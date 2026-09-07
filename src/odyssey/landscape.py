"""Рельеф «Одиссеи»: море, острова, перешейки.

Первая версия карты была ровным лугом, а маршрут держался на стенах из
объектов. Это оказалось и некрасиво, и неработоспособно: кольцевой коридор
обходится по углам, а «скалы», которыми я его перегораживал, при ближайшем
рассмотрении оказались монолитами — то есть телепортами.

Здесь всё иначе. Карта — это море, в котором лежат острова, по одному на
эпизод. Вода непроходима без корабля, поэтому порядок странствия следует из
географии, а не из расстановки препятствий. Для «Одиссеи» это ещё и
единственно верная форма: поэма про морской путь.

Перешейки соединяют только соседние по маршруту острова, так что срезать
дорогу физически негде.
"""

from __future__ import annotations

import logging

from h3m import defaults
from h3m.mapfile import H3Map
from h3m.terrain import Terrain
from odyssey import design

log = logging.getLogger(__name__)

ISLAND_RADIUS = 2
"""Радиус обычного острова.

Три клетки казались естественнее, но при них ближние острова смыкались
берегами: между Троей и Исмаром всего семь клеток, и суша шла сплошняком.
Горловины не возникало, а с ней пропадал и смысл охраны.
"""

FINALE_RADIUS = 6
"""Итака крупнее прочих — на ней стоит город и стоят женихи."""

ISTHMUS_WIDTH = 0
"""Половина ширины перешейка. Ноль означает дорожку в одну клетку.

Узость намеренная: широкий перешеек превращается в обход.
"""

TOWN_ISLAND_RADIUS = 3
"""Остров со стартовым городом чуть крупнее обычного.

Отпечаток города — пять клеток на три, и на пятачке радиусом два он вылезает
в море. Город, частично стоящий на воде, роняет редактор.

Больше трёх делать нельзя: остров Трои дотянется до Исмара, берега сомкнутся,
и горловина между ними исчезнет вместе со смыслом охраны.
"""


def _view(terrain: int, x: int, y: int) -> int:
    """Вид тайла из набора заливки, детерминированно от координат."""
    views = defaults.plain_views(terrain)
    return views[(x * 7 + y * 13) % len(views)]


def _blob(
    parsed: H3Map, center: tuple[int, int, int], radius: int, terrain: int
) -> None:
    """Залить пятно вокруг точки, скругляя углы."""
    size = parsed.header.size
    cx, cy, cz = center

    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            # Скругление: пропускаем самые дальние углы, иначе остров
            # выглядит квадратом, а не сушей.
            if abs(dx) + abs(dy) > radius + radius // 2:
                continue
            x, y = cx + dx, cy + dy
            if 0 <= x < size and 0 <= y < size:
                parsed.terrain.set_tile(x, y, cz, terrain, _view(terrain, x, y))


def _path(
    parsed: H3Map,
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    terrain: int,
    half_width: int,
) -> set[tuple[int, int, int]]:
    """Проложить перешеек между двумя точками буквой «Г».

    Возвращает занятые тропой клетки: их потом резервируют под проход, иначе
    любой объект, севший на дорожку шириной в клетку, запечатает её наглухо.
    """
    size = parsed.header.size
    x0, y0, z = start
    x1, y1, _ = end
    carved: set[tuple[int, int, int]] = set()

    def carve(x: int, y: int) -> None:
        for dy in range(-half_width, half_width + 1):
            for dx in range(-half_width, half_width + 1):
                nx, ny = x + dx, y + dy
                if 0 <= nx < size and 0 <= ny < size:
                    parsed.terrain.set_tile(nx, ny, z, terrain, _view(terrain, nx, ny))
                    carved.add((nx, ny, z))

    step = 1 if x1 >= x0 else -1
    for x in range(x0, x1 + step, step):
        carve(x, y0)

    step = 1 if y1 >= y0 else -1
    for y in range(y0, y1 + step, step):
        carve(x1, y)

    return carved


def _narrowest(
    carved: set[tuple[int, int, int]],
    start: tuple[int, int, int],
    end: tuple[int, int, int],
) -> tuple[int, int, int] | None:
    """Клетка перешейка, самая дальняя от обоих островов.

    Там суша уже всего, и там имеет смысл ставить охрану: обойти негде, кругом
    море. Ставить стража на острове бессмысленно — его просто минуют.
    """
    if not carved:
        return None

    def distance(spot, other):
        return abs(spot[0] - other[0]) + abs(spot[1] - other[1])

    return max(carved, key=lambda spot: min(distance(spot, start), distance(spot, end)))


def paint(parsed: H3Map) -> tuple[set[tuple[int, int, int]], dict[str, tuple[int, int, int]]]:
    """Нарисовать архипелаг и вернуть клетки перешейков.

    Клетки возвращаются, чтобы расстановка объектов их обходила: тропа шириной
    в клетку — единственная связь между островами, и один знак, поставленный
    на ней, режет маршрут пополам.
    """
    if parsed.terrain is None:
        raise ValueError("рельеф не разобран")

    gates: dict[str, tuple[int, int, int]] = {}

    parsed.terrain.fill(Terrain.WATER, defaults.plain_views(Terrain.WATER))
    log.info("Море залито: %d тайлов", parsed.terrain.tile_count)

    surface = [episode for episode in design.ROUTE if episode.anchor[2] == 0]

    for episode in surface:
        radius = ISLAND_RADIUS
        if episode.kind is design.Kind.FINALE:
            radius = FINALE_RADIUS
        elif episode.kind is design.Kind.START:
            radius = TOWN_ISLAND_RADIUS
        _blob(parsed, episode.anchor, radius, Terrain.GRASS)

    for ambush in design.POSEIDON_AMBUSHES:
        _blob(parsed, ambush.position, 1, Terrain.GRASS)

    # Перешейки прокладываются последними, поверх всего.
    #
    # Порядок здесь не косметика: скалы-украшения ложатся по краям островов и,
    # попав на дорожку шириной в клетку, запечатывают её наглухо. В первой
    # версии из-за этого оказались отрезаны пять эпизодов из одиннадцати.
    isthmuses: set[tuple[int, int, int]] = set()
    for previous, following in zip(surface, surface[1:]):
        carved = _path(
            parsed, previous.anchor, following.anchor, Terrain.GRASS, ISTHMUS_WIDTH
        )
        isthmuses |= carved
        gate = _narrowest(carved, previous.anchor, following.anchor)
        if gate is not None:
            gates[following.key] = gate

    _paint_underworld(parsed)

    counts = parsed.terrain.terrain_histogram()
    log.info(
        "Суша %d, море %d, скалы %d, перешейков %d клеток",
        counts.get(int(Terrain.GRASS), 0),
        counts.get(int(Terrain.WATER), 0),
        counts.get(int(Terrain.ROCK), 0),
        len(isthmuses),
    )
    return isthmuses, gates


def _paint_underworld(parsed: H3Map) -> None:
    """Подземелье: сплошная скала и вырубленная в ней пещера Аида."""
    if parsed.header.levels < 2:
        return

    size = parsed.header.size
    for y in range(size):
        for x in range(size):
            parsed.terrain.set_tile(
                x, y, 1, Terrain.ROCK, _view(Terrain.ROCK, x, y)
            )

    hades = design.episode("hades")
    _blob(parsed, hades.anchor, ISLAND_RADIUS + 1, Terrain.SUBTERRANEAN)
