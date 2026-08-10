"""Проверки генерации карт с нуля.

В отличие от остальных тестов, этим не нужна установленная игра: карта
создаётся из ничего. Но именно поэтому они и слабее — доказать, что файл
примет редактор, тесты не могут. Они доказывают, что файл устроен так же, как
настоящие карты, а это необходимое условие, а не достаточное.
"""

from __future__ import annotations

import pytest

from h3m import defaults, generate, mapfile
from h3m.format import MapFormat
from h3m.terrain import TILE_SIZE, Terrain

FILE_TRAILING = 124


def build(**kwargs) -> bytes:
    return mapfile.serialize(generate.new_map("Тест", **kwargs))


def test_generated_map_parses_to_the_very_end() -> None:
    """Сгенерированная карта читается до последнего байта.

    Главный тест генератора. Наш ридер проверен на 157 настоящих картах и
    доходит в них ровно до конца; если он так же проходит нашу карту, значит
    она устроена как настоящая, а не как «понятная только нам самим».
    """
    parsed = mapfile.parse(build())

    assert parsed.stopped_at is None
    assert parsed.tail == b""
    assert parsed.events is not None
    assert len(parsed.events.trailing) == FILE_TRAILING


def test_generated_map_roundtrips() -> None:
    data = build()
    assert mapfile.serialize(mapfile.parse(data)) == data


def test_header_matches_request() -> None:
    parsed = mapfile.parse(build(size=72, two_levels=True, players=4))

    assert parsed.header.format is MapFormat.SOD
    assert parsed.header.size == 72
    assert parsed.header.levels == 2
    assert len(parsed.playable_players) == 4


def test_terrain_fills_whole_map() -> None:
    parsed = mapfile.parse(build(size=36, two_levels=True, terrain=Terrain.SAND))

    assert parsed.terrain is not None
    assert len(parsed.terrain.data) == 36 * 36 * 2 * TILE_SIZE
    assert parsed.terrain.terrain_histogram() == {int(Terrain.SAND): 36 * 36 * 2}
    assert parsed.terrain.tile(0, 0, 1).terrain == Terrain.SAND


def test_masks_come_from_real_maps() -> None:
    """Маски разрешённого взяты из настоящих карт, а не собраны «разрешить всё».

    Ровно на этом упала первая сгенерированная карта: я разрешил всех 156
    героев и не запретил ни одного артефакта, и редактор вылетел. В настоящих
    картах часть содержимого исключена самой игрой, и попытка её включить —
    не щедрая настройка, а невалидные данные.
    """
    parsed = mapfile.parse(build())
    meta = parsed.meta
    assert meta is not None

    assert meta.allowed_heroes.data == defaults.ALLOWED_HEROES_SOD
    assert meta.allowed_heroes.allowed < parsed.header.features.heroes

    assert meta.allowed_artifacts is not None
    assert meta.allowed_artifacts.data == defaults.BANNED_ARTIFACTS_SOD
    assert meta.allowed_artifacts.allowed > 0


def test_terrain_views_are_fill_tiles() -> None:
    """Вид каждого тайла — из набора заливки для своего рельефа.

    Второй виновник падения: рельеф был залит видом номер ноль, которого в
    настоящих картах для травы не встречается вовсе.
    """
    parsed = mapfile.parse(build(terrain=Terrain.GRASS))
    assert parsed.terrain is not None

    allowed = set(defaults.plain_views(Terrain.GRASS))
    data = parsed.terrain.data
    used = {data[offset + 1] for offset in range(0, len(data), TILE_SIZE)}

    assert used <= allowed
    assert len(used) > 1, "вся карта одним видом тайла выглядит неестественно"


def test_generation_is_deterministic() -> None:
    """Одни и те же параметры дают побайтово одинаковый файл."""
    assert build(seed=7) == build(seed=7)
    assert build(seed=1) != build(seed=2)


def test_unplayable_player_stub_marks_no_hero() -> None:
    """В огрызке неиграбельного игрока байт стартового героя равен 0xFF.

    Огрызок выглядит выравниванием, но им не является: на позиции 7 лежит
    стартовый герой, и 0xFF означает «героя нет». Ноль означал бы ссылку на
    героя номер 0 у игрока, которого не существует, — именно из-за этого
    редактор вылетал на первой карте, собранной с нуля.

    Во всех 183 огрызках всех карт SoD из поставки там стоит 0xFF, без
    единого исключения.
    """
    parsed = mapfile.parse(build(players=3))

    stubs = [player for player in parsed.players if not player.is_playable]
    assert len(stubs) == 5
    for stub in stubs:
        assert len(stub.unplayable_padding) == 13  # SoD
        assert stub.unplayable_padding[7] == 0xFF


@pytest.mark.parametrize("size", [35, 100, 0, -1])
def test_invalid_size_is_rejected(size: int) -> None:
    with pytest.raises(ValueError, match="размер"):
        generate.new_map("Тест", size=size)


@pytest.mark.parametrize("players", [0, 9])
def test_invalid_player_count_is_rejected(players: int) -> None:
    with pytest.raises(ValueError, match="игроков"):
        generate.new_map("Тест", players=players)


def test_cyrillic_survives_roundtrip() -> None:
    """Русские название и описание не портятся при записи и чтении."""
    name = "Одиссея"
    description = "Долгий путь домой."

    parsed = mapfile.parse(
        mapfile.serialize(generate.new_map(name, description))
    )

    assert parsed.header.name_text == name
    assert parsed.header.description_text == description
