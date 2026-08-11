"""Показать дизайн карты «Одиссея»: проверка и схема маршрута.

Дизайн проверяется до всякой генерации — опечатка в ключе эпизода или опора за
границами карты обнаруживаются здесь, а не после сборки файла.

Схема рисуется в консоли: 36x36 слишком мелко для деталей, но расположение
эпизодов и длину переходов видно сразу, а это то, что и нужно обсуждать.

Запуск:
    python tools/show_design.py
"""

from __future__ import annotations

import logging

from h3m.logging_setup import setup_logging
from odyssey import design

log = logging.getLogger("show_design")

CELL_EMPTY = "·"


def draw(level: int) -> list[str]:
    """Схема одного слоя: буквы — эпизоды, точки — пустое место."""
    grid = [[CELL_EMPTY] * design.MAP_SIZE for _ in range(design.MAP_SIZE)]

    for number, episode in enumerate(design.ROUTE, start=1):
        x, y, z = episode.anchor
        if z == level:
            grid[y][x] = f"{number:X}"  # до 15 эпизодов помещается в один знак
        if episode.entrance and level == 0:
            ex, ey, _ = episode.entrance
            grid[ey][ex] = "v"  # спуск под землю

    if level == 0:
        for ambush in design.POSEIDON_AMBUSHES:
            ax, ay, _ = ambush.position
            grid[ay][ax] = "*"  # засада Посейдона

    return ["".join(row) for row in grid]


def main() -> None:
    log_path = setup_logging("show_design")

    problems = design.validate()
    if problems:
        log.error("Дизайн несогласован:")
        for problem in problems:
            log.error("  %s", problem)
    else:
        log.info("Дизайн согласован: %d эпизодов", len(design.ROUTE))

    log.info("")
    log.info("«%s» — %dx%d%s, игроков %d",
             design.MAP_NAME, design.MAP_SIZE, design.MAP_SIZE,
             " + подземелье" if design.UNDERGROUND else "", design.PLAYER_COUNT)
    log.info("Победа: %s. Поражение: %s.",
             design.VICTORY.condition, design.VICTORY.loss)

    for level in (0, 1):
        marks = [e for e in design.ROUTE if e.anchor[2] == level]
        if not marks:
            continue
        log.info("")
        log.info("=== %s ===", "Поверхность" if level == 0 else "Подземелье")
        for row_number, row in enumerate(draw(level)):
            if row.strip(CELL_EMPTY):
                log.info("  %2d %s", row_number, row)

    log.info("")
    log.info("=== Маршрут ===")
    for number, episode in enumerate(design.ROUTE, start=1):
        x, y, z = episode.anchor
        where = f"({x:2d},{y:2d})" + ("↓" if z else " ")
        gate = f" ← только после «{design.episode(episode.requires).title}»" \
            if episode.requires else ""
        log.info("  %X. %-26s %s %-14s %s%s",
                 number, episode.title, where, episode.kind.value,
                 episode.idea.split(".")[0], gate)

    log.info("")
    log.info("=== Гнев Посейдона ===")
    for ambush in design.POSEIDON_AMBUSHES:
        x, y, _ = ambush.position
        log.info("  * (%2d,%2d) между «%s» и «%s»: %s",
                 x, y,
                 design.episode(ambush.between[0]).title,
                 design.episode(ambush.between[1]).title,
                 ambush.creatures)

    log.info("")
    log.info("Подробный лог: %s", log_path)


if __name__ == "__main__":
    main()
