"""Создать карту с нуля и проверить её собственным ридером.

Проверка здесь двухступенчатая:

1. сгенерированная карта разбирается нашим же ридером и доходит **ровно до
   конца файла** — с хвостом в 124 байта, как у настоящих карт;
2. повторная сборка после разбора даёт те же байты.

Второе — это тот самый round-trip, который держится на 221 реальной карте.
Первое важнее: оно означает, что карта устроена так же, как настоящие, а не
просто «наш ридер понимает то, что написал наш райтер».

Окончательную проверку даёт только редактор: наш ридер не знает, существует ли
объект с таким спрайтом и проходима ли клетка. Поэтому файл кладётся в out/,
откуда его открывают руками.

Запуск:
    python tools/make_map.py
"""

from __future__ import annotations

import logging

from h3m import generate, mapfile, paths
from h3m.container import read_map_bytes
from h3m.logging_setup import setup_logging
from h3m.terrain import Terrain

log = logging.getLogger("make_map")

EXPECTED_TRAILING = 124


def verify(data: bytes) -> bool:
    """Разобрать сгенерированную карту и убедиться, что она устроена штатно."""
    parsed = mapfile.parse(data)

    problems: list[str] = []

    if parsed.stopped_at:
        problems.append(f"разбор остановлен: {parsed.stopped_at}")
    if parsed.events is None:
        problems.append("блок глобальных событий не разобран")
    elif len(parsed.events.trailing) != EXPECTED_TRAILING:
        problems.append(
            f"хвост файла {len(parsed.events.trailing)} байт "
            f"вместо {EXPECTED_TRAILING}"
        )
    if parsed.tail:
        problems.append(f"осталось {len(parsed.tail)} неразобранных байт")
    if not parsed.playable_players:
        problems.append("нет ни одного играбельного игрока")

    rebuilt = mapfile.serialize(parsed)
    if rebuilt != data:
        problems.append("round-trip не сошёлся")

    for problem in problems:
        log.error("  %s", problem)

    if not problems:
        log.info("  разобрана до конца, round-trip сошёлся")
        log.info("  %s", parsed.header)
        log.info(
            "  игроков: %d, тайлов: %d, объектов: %d",
            len(parsed.playable_players),
            generate.tile_count(parsed),
            len(parsed.objects or []),
        )
    return not problems


def main() -> None:
    log_path = setup_logging("make_map")

    parsed = generate.new_map(
        name="Проба пера",
        description="Пустая карта, созданная h3m-forge с нуля.",
        size=36,
        players=2,
        terrain=Terrain.GRASS,
    )

    data = mapfile.serialize(parsed)
    log.info("Собрано байт: %d", len(data))

    log.info("Проверка собственным ридером:")
    ok = verify(data)

    out_path = paths.out_dir() / "blank.h3m"
    mapfile.save(out_path, parsed)
    log.info("")
    log.info("Карта записана: %s (%d байт на диске)",
             out_path, out_path.stat().st_size)

    # Сверяем с настоящей картой того же размера — просто чтобы видеть порядок.
    for real in paths.iter_maps():
        real_data = read_map_bytes(real)
        real_map = mapfile.parse(real_data)
        if real_map.header.size == 36 and real_map.header.levels == 1:
            log.info(
                "Для сравнения, настоящая карта %s: %d байт распакованных",
                real.name,
                len(real_data),
            )
            break

    log.info("")
    log.info("Итог: %s", "готово" if ok else "ЕСТЬ ПРОБЛЕМЫ")
    log.info("Подробный лог: %s", log_path)


if __name__ == "__main__":
    main()
