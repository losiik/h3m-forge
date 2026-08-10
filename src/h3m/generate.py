"""Создание карт с нуля.

Строим не байты, а те же структуры, что получает ридер, — и отдаём их тому же
райтеру. Значит, вся уверенность, накопленная round-trip'ом на 157 реальных
картах, распространяется и на сгенерированные: если структура собирается в
байты правильно для чужих карт, она соберётся правильно и для наших.

Целевой формат — SoD. Он разобран на 100%, тогда как в HotA остаются
неустановленные поля. Редактор HotA открывает SoD-карты штатно, так что
ограничение чисто внутреннее.
"""

from __future__ import annotations

import logging

from h3m import conditions, defaults, options
from h3m.events import EventsBlock
from h3m.format import MapFeatures, MapFormat, features_for
from h3m.header import MapHeader
from h3m.heroes import PredefinedHeroes
from h3m.mapfile import H3Map
from h3m.players import NO_HERO, PLAYER_COUNT, PlayerInfo
from h3m.terrain import TILE_SIZE, Terrain, TerrainMap

log = logging.getLogger(__name__)

DEFAULT_ENCODING = "cp1251"

FILE_TRAILING = b"\x00" * 124
"""Хвост нулей в конце файла — есть у всех карт из поставки."""

RESERVED_ZEROS = b"\x00" * options.RESERVED_ZEROS

#: Все девять фракций SoD.
ALL_FACTIONS = 0x01FF

VALID_SIZES = (36, 72, 108, 144)


class Difficulty:
    """Уровень сложности карты."""

    EASY = 0
    NORMAL = 1
    HARD = 2
    EXPERT = 3
    IMPOSSIBLE = 4


def _encode(text: str) -> bytes:
    return text.encode(DEFAULT_ENCODING, errors="replace")


def _playable_player(faction_mask: int = ALL_FACTIONS) -> PlayerInfo:
    return PlayerInfo(
        can_human_play=1,
        can_computer_play=1,
        ai_tactic=defaults.DEFAULT_AI_TACTIC,
        sod_faction_flag=b"\x00",
        allowed_factions=faction_mask,
        is_faction_random=1,
        has_main_town=0,
        has_random_hero=0,
        main_custom_hero_id=NO_HERO,
        ab_padding=b"\x00",
    )


def _unplayable_player(features: MapFeatures) -> PlayerInfo:
    stub = defaults.UNPLAYABLE_PLAYER_STUB_SOD
    if len(stub) != features.unplayable_player_padding:
        raise ValueError(
            f"огрызок неиграбельного игрока {len(stub)} байт, "
            f"а формат ждёт {features.unplayable_player_padding}"
        )
    return PlayerInfo(
        can_human_play=0,
        can_computer_play=0,
        unplayable_padding=stub,
    )


def _flat_terrain(size: int, levels: int, terrain: int, seed: int) -> TerrainMap:
    """Однородный рельеф без рек и дорог.

    Вид тайла меняется от клетки к клетке: в игре сплошная область покрывается
    несколькими вариантами вперемешку, и одинаковый вид на всей карте выглядел
    бы неестественно. Выбор детерминированный — от координат, а не от
    генератора случайных чисел, чтобы одна и та же карта собиралась байт в байт
    при каждом запуске.
    """
    views = defaults.plain_views(terrain)
    tiles = bytearray()

    for index in range(size * size * levels):
        view = views[(index * 2654435761 + seed) % len(views)]
        tiles += bytes([terrain, view, 0, 0, 0, 0, 0])

    return TerrainMap(data=bytes(tiles), size=size, levels=levels)


def new_map(
    name: str,
    description: str = "",
    *,
    size: int = 36,
    two_levels: bool = False,
    players: int = 2,
    terrain: int = Terrain.GRASS,
    seed: int = 0,
    difficulty: int = Difficulty.NORMAL,
) -> H3Map:
    """Создать пустую, но валидную карту.

    Без объектов и без стартовых городов: это фундамент, на который дальше
    кладётся содержимое. Такая карта уже открывается в редакторе.
    """
    if size not in VALID_SIZES:
        raise ValueError(f"недопустимый размер карты: {size}; можно {VALID_SIZES}")
    if not 1 <= players <= PLAYER_COUNT:
        raise ValueError(f"игроков должно быть от 1 до {PLAYER_COUNT}, а не {players}")

    features = features_for(MapFormat.SOD)
    levels = 2 if two_levels else 1

    header = MapHeader(
        format=MapFormat.SOD,
        features=features,
        any_players=1,
        size=size,
        two_levels=1 if two_levels else 0,
        name=_encode(name),
        description=_encode(description),
        difficulty=difficulty,
        level_limit=0,
    )

    player_list = [_playable_player() for _ in range(players)]
    player_list += [
        _unplayable_player(features) for _ in range(PLAYER_COUNT - players)
    ]

    meta = options.MapMeta(
        teams=options.TeamInfo(count=0),
        # Маски берутся из настоящих карт, а не собираются «разрешить всё»:
        # часть героев и артефактов игра исключает сама, и попытка их
        # разрешить роняет редактор.
        allowed_heroes=options.SizedMask(defaults.ALLOWED_HEROES_SOD),
        hero_placeholders=[],
        disposed_heroes=[],
        options=options.MapOptions(reserved=RESERVED_ZEROS),
        hota_scripts_flag=b"",
        allowed_artifacts=options.SizedMask(defaults.BANNED_ARTIFACTS_SOD),
        allowed_spells=defaults.BANNED_SPELLS_SOD,
        allowed_skills=defaults.BANNED_SKILLS_SOD,
        rumors=[],
    )

    parsed = H3Map(
        header=header,
        players=player_list,
        victory=conditions.VictoryCondition(kind=conditions.STANDARD),
        loss=conditions.LossCondition(kind=conditions.STANDARD),
        meta=meta,
        predefined_heroes=PredefinedHeroes(),
        terrain=_flat_terrain(size, levels, terrain, seed),
        object_templates=[],
        objects=[],
        events=EventsBlock(events=[], trailing=FILE_TRAILING),
        tail=b"",
    )

    log.debug(
        "Создана карта %dx%d, слоёв %d, игроков %d", size, size, levels, players
    )
    return parsed


def tile_count(parsed: H3Map) -> int:
    """Сколько тайлов в карте — удобство для проверок."""
    return len(parsed.terrain.data) // TILE_SIZE if parsed.terrain else 0
