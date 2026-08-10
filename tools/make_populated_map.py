"""Карты с содержимым: украшения и стартовые города.

Делается сразу два файла, чтобы одна проверка в редакторе разделяла две
независимые новые возможности:

* ``objects.h3m`` — только украшения. Проверяет запись объектов как таковую:
  таблицу шаблонов, ссылки на неё, координаты. Начинки у украшений нет, так
  что ошибиться в ней невозможно.
* ``towns.h3m`` — то же плюс два стартовых города. Добавляет к проверке
  начинку города и связь «объект — запись игрока».

Если откроется первый и не откроется второй, виноваты города, а не механизм
расстановки. Если оба — обе возможности работают.

Запуск:
    python tools/make_populated_map.py
"""

from __future__ import annotations

import logging

from h3m import catalog, generate, mapfile, paths
from h3m.logging_setup import setup_logging
from h3m.terrain import Terrain

log = logging.getLogger("make_populated")

SIZE = 36
TERRAIN = Terrain.GRASS

#: Позиции украшений: две рощи по краям, подальше от городов.
DECORATION_SPOTS = [
    (6, 6), (8, 7), (7, 10), (10, 9), (5, 12),
    (28, 24), (26, 27), (29, 28), (24, 26), (27, 22),
    (17, 17), (18, 19), (16, 20),
]

#: Стартовые города: координаты объекта, не записи игрока.
TOWN_SPOTS = [(10, 28), (28, 8)]


def describe(parsed: mapfile.H3Map) -> None:
    log.info("  %s", parsed.header)
    log.info(
        "  шаблонов %d, объектов %d, игроков %d",
        len(parsed.object_templates or []),
        len(parsed.objects or []),
        len(parsed.playable_players),
    )
    for index, player in enumerate(parsed.players):
        if player.has_main_town:
            log.info("    игрок %d: город в записи %s", index, player.main_town_pos)


def verify(parsed: mapfile.H3Map) -> bool:
    """Карта должна читаться до конца и собираться обратно байт в байт."""
    data = mapfile.serialize(parsed)
    again = mapfile.parse(data)

    problems = []
    if again.stopped_at:
        problems.append(f"разбор остановлен: {again.stopped_at}")
    if again.tail:
        problems.append(f"осталось {len(again.tail)} байт")
    if mapfile.serialize(again) != data:
        problems.append("round-trip не сошёлся")

    for problem in problems:
        log.error("  %s", problem)
    return not problems


def build_decorated() -> mapfile.H3Map:
    parsed = generate.new_map(
        name="Проба: украшения",
        description="Пустая карта с деревьями. Проверка записи объектов.",
        size=SIZE,
        players=2,
        terrain=TERRAIN,
    )

    decorations = catalog.borrow_decorations(limit=5, terrain=TERRAIN)
    log.info("Заимствовано украшений: %d", len(decorations))
    for item in decorations:
        log.info("  %s", item)

    if not decorations:
        raise RuntimeError("не нашлось украшений, допустимых на этом рельефе")

    for number, (x, y) in enumerate(DECORATION_SPOTS):
        catalog.place(parsed, decorations[number % len(decorations)], x, y)

    return parsed


def build_with_towns() -> mapfile.H3Map:
    parsed = build_decorated()
    parsed.header.name = "Проба: города".encode(generate.DEFAULT_ENCODING)
    parsed.header.description = (
        "Два стартовых города и деревья.".encode(generate.DEFAULT_ENCODING)
    )

    for player_index, (x, y) in enumerate(TOWN_SPOTS):
        generate.place_starting_town(parsed, player_index, x, y)

    return parsed


def main() -> None:
    log_path = setup_logging("make_populated")

    for filename, builder in (
        ("objects.h3m", build_decorated),
        ("towns.h3m", build_with_towns),
    ):
        log.info("")
        log.info("=== %s ===", filename)
        parsed = builder()
        describe(parsed)

        if not verify(parsed):
            log.error("  собственная проверка не пройдена, файл не пишется")
            continue

        out_path = paths.out_dir() / filename
        mapfile.save(out_path, parsed)
        log.info("  записано: %s (%d байт)", out_path, out_path.stat().st_size)

    log.info("")
    log.info("Подробный лог: %s", log_path)


if __name__ == "__main__":
    main()
