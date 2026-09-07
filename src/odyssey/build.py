"""Сборка карты «Одиссея» из дизайна.

Дизайн описывает замысел словами, здесь он превращается в объекты. Разделение
намеренное: сюжет правится в `design.py` без единой мысли о байтах, а числа
живут тут.

Начинка табличек и монстров собирается по полям (`h3m.build`), шаблоны
объектов заимствуются из карт поставки (`h3m.catalog`) — сочинять имена
спрайтов и маски проходимости нельзя, это проверено дорогой ценой.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from h3m import build, catalog, conditions, generate, mapfile
from h3m.objtypes import Obj
from h3m.terrain import Terrain
from odyssey import design, landscape
from odyssey.creatures import Creature

log = logging.getLogger(__name__)

ENCODING = "cp1251"

#: Игрок, за которого играют. Одиссей один, союзников нет.
ODYSSEUS = 0

#: Смещение таблички относительно опоры эпизода: на подходе, а не поверх.
SIGN_OFFSET = (-2, 1)


@dataclass(frozen=True, slots=True)
class Guard:
    """Кто стоит в эпизоде и сколько его.

    Ноль означает «на усмотрение игры»: количество подберётся под силу карты.
    Так делает и редактор, когда число не задано вручную.
    """

    creature: Creature
    count: int = 0
    character: int = build.Character.HOSTILE
    offset: tuple[int, int] = (0, 0)


#: Кто охраняет каждый эпизод. Ключи — из design.ROUTE.
GUARDS: dict[str, tuple[Guard, ...]] = {
    "ismarus": (Guard(Creature.SWORDSMAN, 12),),
    "polyphemus": (Guard(Creature.CYCLOPS_KING, 9, offset=(1, 0)),),
    "laestrygonians": (
        Guard(Creature.OGRE, 30, offset=(-1, 0)),
        Guard(Creature.OGRE, 25, offset=(1, 1)),
    ),
    "circe": (Guard(Creature.BOAR, 20, character=build.Character.COMPLIANT),),
    "hades": (Guard(Creature.WIGHT, 25),),
    "sirens": (Guard(Creature.HARPY_HAG, 40),),
    "scylla": (
        Guard(Creature.HYDRA, 8, offset=(-1, 0)),
        Guard(Creature.SWORDSMAN, 60, offset=(2, 0)),
    ),
    "helios": (Guard(Creature.BEHEMOTH, 6, character=build.Character.COMPLIANT),),
    "ithaca": (
        Guard(Creature.SWORDSMAN, 120, offset=(-2, 1)),
        Guard(Creature.SWORDSMAN, 90, offset=(2, 1)),
    ),
}

#: Существа засад Посейдона — по одному виду на засаду, сила растёт.
AMBUSH_GUARDS: dict[str, Guard] = {
    "wrath_first": Guard(Creature.WATER_ELEMENTAL, 15),
    "wrath_second": Guard(Creature.WATER_ELEMENTAL, 30),
    "wrath_third": Guard(Creature.NAGA, 14),
    "wrath_last": Guard(Creature.ICE_ELEMENTAL, 40),
}


TOKEN_ARTIFACT = 7
"""Знак Тиресия — предмет, который Аид выдаёт, а страж перед Итакой требует.

Классический для Heroes III способ связать два места на карте: без него
«условие возвращения» из пророчества осталось бы словами на табличке.
Номер выбран из тех, что встречаются в картах поставки; имена артефактов в
шаблонах обезличены (AVA0007.def), так что смысловой подбор невозможен.
"""

#: Смещение города Итаки от опорной точки эпизода.
#:
#: Якорь города — правый нижний угол его отпечатка 5x3, поэтому объект,
#: поставленный ровно в опору, занимает левую половину кольца, а справа
#: остаётся пусто. Смещение возвращает город в середину.
ITHACA_TOWN_OFFSET = (2, 1)

#: Награды за эпизоды. Дерево, ртуть, руда, сера, кристаллы, самоцветы, золото.
REWARDS: dict[str, dict] = {
    "ismarus": {"resources": (5, 0, 5, 0, 0, 0, 2000)},
    "lotus": {"resources": (10, 3, 10, 3, 3, 3, 5000)},
    "polyphemus": {"artifacts": (9,)},
    "aeolus": {"artifacts": (12,)},
    "helios": {"resources": (0, 5, 0, 5, 5, 5, 3000)},
}


#: Смещение стартового города от опоры эпизода. Причина та же, что у Итаки:
#: отпечаток города растёт влево от якоря, и на маленьком острове без сдвига
#: он вылезает в море.
TROY_TOWN_OFFSET = (2, 0)


def troy_town_position() -> tuple[int, int, int]:
    """Где на самом деле стоит город Трои."""
    x, y, z = design.episode("troy").anchor
    return x + TROY_TOWN_OFFSET[0], y + TROY_TOWN_OFFSET[1], z


def ithaca_town_position() -> tuple[int, int, int]:
    """Где на самом деле стоит город Итаки.

    Опорная точка эпизода и позиция объекта — разные вещи: город смещён, чтобы
    встать в середину кольца. Раз это знание нужно и сборке, и условию победы,
    и проверкам, оно живёт в одном месте.
    """
    x, y, z = design.episode("ithaca").anchor
    return x + ITHACA_TOWN_OFFSET[0], y + ITHACA_TOWN_OFFSET[1], z


def _encode(text: str) -> bytes:
    return text.encode(ENCODING, errors="replace")


def _clamp(value: int, limit: int) -> int:
    return max(0, min(value, limit - 1))


def _is_land(parsed: mapfile.H3Map, spot: tuple[int, int, int]) -> bool:
    """Можно ли ставить объект на эту клетку.

    Объект в море — не просто странно выглядит: город, чей отпечаток вылез на
    воду, роняет редактор. Проверка обязательна для карты-архипелага.
    """
    terrain = parsed.terrain.tile(*spot).terrain
    return terrain not in (Terrain.WATER, Terrain.ROCK)


def _free_spot(
    parsed: mapfile.H3Map,
    x: int,
    y: int,
    z: int,
    reserved: frozenset[tuple[int, int, int]] = frozenset(),
) -> tuple[int, int, int]:
    """Ближайшая к ``(x, y)`` свободная клетка того же слоя.

    Объекты нельзя ставить друг на друга: верхний просто скрывает нижний, и
    карта молча теряет содержимое. Именно так с первой сборки пропали три
    таблички — они оказались под отрядом, под ящиком и под другой табличкой.
    Ни round-trip, ни разбор такого не замечают: файл-то корректен.
    """
    size = parsed.header.size
    taken = {(o.x, o.y, o.z) for o in (parsed.objects or [])} | set(reserved)

    for radius in range(0, size):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                spot = (_clamp(x + dx, size), _clamp(y + dy, size), z)
                if spot in taken or not _is_land(parsed, spot):
                    continue
                return spot

    raise ValueError(f"не нашлось свободной клетки рядом с ({x}, {y}, {z})")


def _place_sign(
    parsed: mapfile.H3Map,
    sign_template,
    x: int,
    y: int,
    z: int,
    text: str,
    reserved: frozenset = frozenset(),
) -> None:
    size = parsed.header.size
    spot = _free_spot(
        parsed,
        _clamp(x + SIGN_OFFSET[0], size),
        _clamp(y + SIGN_OFFSET[1], size),
        z,
        reserved,
    )
    catalog.place(parsed, sign_template, *spot, payload=build.sign_payload(_encode(text)))


def _template(parsed: mapfile.H3Map, cache: dict, object_id: int):
    """Заимствовать шаблон объекта один раз и переиспользовать."""
    if object_id not in cache:
        cache[object_id] = catalog.borrow(object_id, with_payload=True)
    return cache[object_id]


def _place_guard(
    parsed: mapfile.H3Map,
    templates: dict[int, object],
    guard: Guard,
    x: int,
    y: int,
    z: int,
    reserved: frozenset = frozenset(),
) -> None:
    size = parsed.header.size
    position = _free_spot(
        parsed,
        _clamp(x + guard.offset[0], size),
        _clamp(y + guard.offset[1], size),
        z,
        reserved,
    )

    template = templates.get(guard.creature)
    if template is None:
        template = catalog.borrow(Obj.MONSTER, subid=int(guard.creature))
        templates[guard.creature] = template

    catalog.place(
        parsed,
        template,
        *position,
        payload=build.monster_payload(
            parsed.header.features,
            position=position,
            count=guard.count,
            character=guard.character,
        ),
    )


def _capture_city_victory(x: int, y: int, z: int) -> conditions.VictoryCondition:
    """Победа: захватить Итаку.

    Обычная победа отключена: противников на карте нет, и оставить её значило
    бы объявить победу в первый же день.
    """
    return conditions.VictoryCondition(
        kind=conditions.VictoryType.CAPTURE_CITY,
        allow_normal_victory=0,
        applies_to_ai=0,
        payload=bytes([x, y, z]),
    )


def build_map() -> mapfile.H3Map:
    """Собрать карту по дизайну."""
    problems = design.validate()
    if problems:
        raise ValueError("дизайн несогласован: " + "; ".join(problems))

    parsed = generate.new_map(
        name=design.MAP_NAME,
        description=design.MAP_DESCRIPTION,
        size=design.MAP_SIZE,
        two_levels=design.UNDERGROUND,
        players=design.PLAYER_COUNT,
        terrain=Terrain.WATER,
    )
    isthmuses, gates = landscape.paint(parsed)
    reserved = frozenset(isthmuses)

    sign_template = catalog.borrow(Obj.SIGN, with_payload=True)
    monsters: dict[int, object] = {}
    templates: dict[int, object] = {}

    for episode in design.ROUTE:
        x, y, z = episode.anchor

        if episode.kind is design.Kind.START:
            # Город смещён вправо: его отпечаток растёт влево от якоря и на
            # маленьком острове иначе вылезает в море.
            generate.place_starting_town(parsed, ODYSSEUS, *troy_town_position())
        elif episode.kind is design.Kind.FINALE:
            town = catalog.borrow(Obj.TOWN, with_payload=True)
            catalog.place(parsed, town, *ithaca_town_position())

        _place_sign(parsed, sign_template, x, y, z, episode.sign, reserved)

        gate = gates.get(episode.key)
        for number, guard in enumerate(GUARDS.get(episode.key, ())):
            if number == 0 and gate is not None:
                # Первый отряд перекрывает горловину: мимо не пройти.
                _place_guard(parsed, monsters, guard, gate[0], gate[1], gate[2])
            else:
                _place_guard(parsed, monsters, guard, x, y, z, reserved)

        reward = REWARDS.get(episode.key)
        if reward is not None:
            catalog.place(
                parsed,
                _template(parsed, templates, Obj.PANDORAS_BOX),
                *_free_spot(
                    parsed,
                    _clamp(x + 1, parsed.header.size),
                    _clamp(y - 1, parsed.header.size),
                    z,
                    reserved,
                ),
                payload=build.pandora_payload(
                    parsed.header.features,
                    message=_encode(episode.aftermath or episode.sign),
                    **reward,
                ),
            )

        if episode.key == "hades":
            catalog.place(
                parsed,
                _template(parsed, templates, Obj.SEER_HUT),
                *_free_spot(parsed, _clamp(x + 1, parsed.header.size), y, z, reserved),
                payload=build.seer_hut_artifact_payload(
                    parsed.header.features,
                    artifact=TOKEN_ARTIFACT,
                    first=_encode(
                        "Тиресий назовёт условие возвращения. "
                        "Возьми знак — без него домой не войдёшь."
                    ),
                    done=_encode(episode.aftermath),
                ),
            )

        if episode.entrance:
            ex, ey, ez = episode.entrance
            _place_sign(parsed, sign_template, ex, ey, ez, "Спуск к мёртвым.", reserved)

    for ambush in design.POSEIDON_AMBUSHES:
        ax, ay, az = ambush.position
        if ambush.sign:
            _place_sign(parsed, sign_template, ax, ay, az, ambush.sign, reserved)
        _place_guard(parsed, monsters, AMBUSH_GUARDS[ambush.key], ax, ay, az, reserved)

    finale = design.episode("ithaca")
    fx, fy, fz = finale.anchor

    # Страж, требующий знак Тиресия, стоит на перешейке к Итаке — там, где
    # суша сужается до одной клетки. Обойти его негде: кругом море.
    previous = design.ROUTE[design.ROUTE.index(finale) - 1]
    catalog.place(
        parsed,
        _template(parsed, templates, Obj.QUEST_GUARD),
        *_free_spot(
            parsed,
            _clamp(fx - landscape.FINALE_RADIUS - 2, parsed.header.size),
            previous.anchor[1],
            fz,
        ),
        payload=build.quest_guard_payload(
            parsed.header.features,
            artifact=TOKEN_ARTIFACT,
            first=_encode(
                "Без знака Тиресия дороги домой нет. Спустись к мёртвым и спроси."
            ),
            done=_encode("Знак при тебе. Проходи."),
        ),
    )


    # Условие победы указывает на сам объект города, а не на опору эпизода.
    parsed.victory = _capture_city_victory(*ithaca_town_position())

    log.info(
        "Собрана «%s»: объектов %d, шаблонов %d",
        design.MAP_NAME,
        len(parsed.objects or []),
        len(parsed.object_templates or []),
    )
    return parsed
