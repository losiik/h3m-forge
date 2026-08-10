"""Основной отчёт проекта: round-trip и доля разобранного.

Две метрики, обе по всем картам из поставки:

* **round-trip** — сколько карт собираются обратно байт в байт. Должно быть
  100% всегда: нераспознанное лежит в хвосте и пишется как есть, так что
  падение этой метрики означает регрессию в уже разобранной части;
* **доля разобранного** — сколько процентов файла разложено на поля, а не
  лежит сырым хвостом. Это и есть прогресс.

Запуск:
    python tools/roundtrip.py
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from h3m import mapfile, paths
from h3m.container import read_map_bytes
from h3m.logging_setup import setup_logging

log = logging.getLogger("roundtrip")


@dataclass(slots=True)
class FormatStats:
    total: int = 0
    roundtrip_ok: int = 0
    parsed_bytes: int = 0
    total_bytes: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)

    @property
    def parsed_fraction(self) -> float:
        return self.parsed_bytes / self.total_bytes if self.total_bytes else 0.0


def first_difference(left: bytes, right: bytes) -> int:
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    if len(left) != len(right):
        return min(len(left), len(right))
    return -1


def check(path: Path, stats: dict[str, FormatStats]) -> None:
    try:
        data = read_map_bytes(path)
    except OSError as exc:
        stats["?"].total += 1
        stats["?"].failures.append((path.name, f"распаковка: {exc}"))
        return

    try:
        parsed = mapfile.parse(data)
    except Exception as exc:  # noqa: BLE001 — интересна любая поломка
        stats["?"].total += 1
        stats["?"].failures.append((path.name, f"{type(exc).__name__}: {exc}"))
        log.debug("Не разобралась %s: %s", path.name, exc)
        return

    entry = stats[parsed.header.format.name]
    entry.total += 1
    entry.parsed_bytes += parsed.parsed_size
    entry.total_bytes += parsed.total_size

    rebuilt = mapfile.serialize(parsed)
    diff = first_difference(data, rebuilt)

    if diff < 0:
        entry.roundtrip_ok += 1
    else:
        entry.failures.append((path.name, f"расхождение на байте {diff}"))
        log.debug("Round-trip не сошёлся: %s на байте %d", path.name, diff)


def main() -> None:
    log_path = setup_logging("roundtrip")

    maps = list(paths.iter_maps())
    log.info("Карт: %d", len(maps))

    stats: dict[str, FormatStats] = defaultdict(FormatStats)
    for map_path in maps:
        check(map_path, stats)

    order = ["ROE", "AB", "SOD", "HOTA", "WOG", "?"]
    present = [key for key in order if key in stats] + [
        key for key in stats if key not in order
    ]

    log.info("")
    log.info("%-6s %7s %12s %10s", "формат", "карт", "round-trip", "разобрано")
    log.info("%s", "-" * 40)

    total = ok = 0
    parsed_bytes = total_bytes = 0

    for key in present:
        entry = stats[key]
        total += entry.total
        ok += entry.roundtrip_ok
        parsed_bytes += entry.parsed_bytes
        total_bytes += entry.total_bytes
        log.info(
            "%-6s %7d %7d/%-4d %9.1f%%",
            key,
            entry.total,
            entry.roundtrip_ok,
            entry.total,
            entry.parsed_fraction * 100,
        )

    log.info("%s", "-" * 40)
    overall = parsed_bytes / total_bytes * 100 if total_bytes else 0.0
    log.info("%-6s %7d %7d/%-4d %9.1f%%", "ИТОГО", total, ok, total, overall)

    failures = [(key, name, why) for key in present for name, why in stats[key].failures]
    if failures:
        log.info("")
        log.warning("Проблемы: %d", len(failures))
        for key, name, why in failures[:20]:
            log.warning("  [%s] %-40s %s", key, name, why)
        if len(failures) > 20:
            log.warning("  ... ещё %d", len(failures) - 20)

    log.info("")
    log.info("Подробный лог: %s", log_path)


if __name__ == "__main__":
    main()
