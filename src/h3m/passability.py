"""Проходимость карты: что перекрыто рельефом и объектами.

Нужна, чтобы проверять замысел, а не только формат. Барьер, который можно
обойти, — валидные данные и бессмысленная карта; ни round-trip, ни разбор
такого не заметят. Здесь считается то же, что видит игрок: куда можно ступить.

Раскладка масок объекта нетривиальна. Шаблон описывает сетку 8x6, где **якорь
объекта — правая нижняя клетка**, а не левая верхняя. Плюс бит проходимости
инвертирован: ноль означает «занято». Отсюда пересчёт координат ниже.
"""

from __future__ import annotations

import logging
from collections import deque

from h3m.mapfile import H3Map
from h3m.objects import ObjectTemplate
from h3m.objtypes import Obj
from h3m.terrain import Terrain

log = logging.getLogger(__name__)

#: Рельефы, по которым пеший герой не ходит.
#:
#: Вода включена намеренно: без корабля она непреодолима, а корабли на карте
#: не расставлены. Скалы непроходимы всегда.
IMPASSABLE_TERRAIN = frozenset({Terrain.ROCK, Terrain.WATER})

#: Объекты, которые перекрывают клетку, но проходятся после взаимодействия.
#:
#: Разница принципиальная: скала — преграда, отряд монстров — препятствие.
#: Если считать их одинаково, любой охраняемый проход выглядит тупиком, и
#: проверка связности объявляет карту непроходимой, хотя она играбельна.
GATE_TYPES = frozenset(
    {
        Obj.MONSTER,
        Obj.RANDOM_MONSTER,
        Obj.RANDOM_MONSTER_L1,
        Obj.RANDOM_MONSTER_L2,
        Obj.RANDOM_MONSTER_L3,
        Obj.RANDOM_MONSTER_L4,
        Obj.RANDOM_MONSTER_L5,
        Obj.RANDOM_MONSTER_L6,
        Obj.RANDOM_MONSTER_L7,
        Obj.QUEST_GUARD,
        Obj.BORDER_GATE,
    }
)


def object_footprint(
    template: ObjectTemplate, x: int, y: int
) -> list[tuple[int, int]]:
    """Клетки карты, которые объект перекрывает."""
    return [(x + dx, y + dy) for dx, dy in template.blocked_cells()]


def blocked_tiles(
    parsed: H3Map, *, gates_passable: bool = True
) -> set[tuple[int, int, int]]:
    """Непроходимые клетки карты: рельеф и объекты.

    :param gates_passable: считать ли охрану проходимой. По умолчанию да —
        монстра можно победить, стража квеста удовлетворить. Если поставить
        ``False``, охрана станет глухой стеной: так проверяют, что проход
        действительно ведёт через неё, а не в обход.
    """
    if parsed.terrain is None:
        raise ValueError("рельеф не разобран")

    size, levels = parsed.header.size, parsed.header.levels
    blocked: set[tuple[int, int, int]] = set()

    for z in range(levels):
        for y in range(size):
            for x in range(size):
                if parsed.terrain.tile(x, y, z).terrain in IMPASSABLE_TERRAIN:
                    blocked.add((x, y, z))

    templates = parsed.object_templates or []
    for instance in parsed.objects or []:
        if gates_passable and instance.object_id in GATE_TYPES:
            continue
        template = templates[instance.template_index]
        for cell_x, cell_y in object_footprint(template, instance.x, instance.y):
            if 0 <= cell_x < size and 0 <= cell_y < size:
                blocked.add((cell_x, cell_y, instance.z))

    return blocked


def reachable(
    parsed: H3Map,
    start: tuple[int, int, int],
    *,
    blocked: set[tuple[int, int, int]] | None = None,
) -> set[tuple[int, int, int]]:
    """Куда можно дойти из ``start``, не покидая своего слоя.

    Переходы между слоями не моделируются: на карте они делаются объектами
    (лестницы, монолиты), у каждого своя механика. Для проверки барьеров
    достаточно связности внутри слоя.
    """
    if blocked is None:
        blocked = blocked_tiles(parsed)

    size = parsed.header.size
    start_x, start_y, level = start

    seen = {(start_x, start_y, level)}
    queue = deque([(start_x, start_y)])

    while queue:
        x, y = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < size and 0 <= ny < size):
                continue
            spot = (nx, ny, level)
            if spot in seen or spot in blocked:
                continue
            seen.add(spot)
            queue.append((nx, ny))

    return seen


def is_reachable(
    parsed: H3Map,
    start: tuple[int, int, int],
    target: tuple[int, int, int],
    *,
    blocked: set[tuple[int, int, int]] | None = None,
) -> bool:
    """Можно ли дойти от ``start`` до ``target`` по своему слою."""
    if start[2] != target[2]:
        return False
    return target in reachable(parsed, start, blocked=blocked)


def can_approach(
    parsed: H3Map,
    start: tuple[int, int, int],
    target: tuple[int, int, int],
    *,
    blocked: set[tuple[int, int, int]] | None = None,
) -> bool:
    """Можно ли подойти к ``target`` вплотную.

    На клетку с объектом герой не встаёт — он подходит к ней и взаимодействует
    с соседней. Поэтому достижимость объекта проверяется по его окрестности, а
    не по его собственной клетке: город, отряд или ящик всегда перекрывают
    место, на котором стоят.
    """
    if start[2] != target[2]:
        return False

    if blocked is None:
        blocked = blocked_tiles(parsed)

    seen = reachable(parsed, start, blocked=blocked)
    x, y, z = target
    return any(
        (x + dx, y + dy, z) in seen
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        if (dx, dy) != (0, 0)
    )
