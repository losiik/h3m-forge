"""Разведка: какие версии формата встречаются в картах из поставки.

Прежде чем писать парсер, полезно узнать, что вообще предстоит парсить.
Файл .h3m — это gzip-контейнер; первые 4 байта распакованного потока — версия
формата (little-endian u32). Дальше у HotA идут собственные поля, которых нет в
SoD, поэтому для HotA-карт дополнительно печатаем следующие байты как есть —
разбираться в них будем позже.

Запуск:
    python tools/scan_versions.py
"""

from __future__ import annotations

import gzip
import logging
import struct
from collections import Counter, defaultdict
from pathlib import Path

from h3m import paths
from h3m.logging_setup import setup_logging

log = logging.getLogger("scan_versions")

#: Известные значения поля версии. Значения RoE/AB/SoD/WoG — общеизвестные,
#: HotA опознаём по 0x20 и уточняем подверсию отдельным полем.
KNOWN_VERSIONS = {
    0x0E: "RoE (Restoration of Erathia)",
    0x15: "AB (Armageddon's Blade)",
    0x1C: "SoD (Shadow of Death)",
    0x20: "HotA (Horn of the Abyss)",
    0x33: "WoG (Wake of Gods)",
}


def read_header_bytes(path: Path, count: int = 24) -> bytes:
    """Распаковать начало карты. Не читаем файл целиком — нужен только заголовок."""
    with gzip.open(path, "rb") as fh:
        return fh.read(count)


def main() -> None:
    log_path = setup_logging("scan_versions")

    maps = list(paths.iter_maps())
    log.info("Найдено карт: %d", len(maps))
    log.info("Каталог: %s", paths.maps_dir())

    versions: Counter[int] = Counter()
    hota_subversions: Counter[int] = Counter()
    examples: dict[int, list[str]] = defaultdict(list)
    broken: list[tuple[str, str]] = []

    for map_path in maps:
        try:
            head = read_header_bytes(map_path)
        except OSError as exc:
            # Не gzip, битый файл или что-то ещё неожиданное — не падаем,
            # а копим список проблемных: он сам по себе информация.
            broken.append((map_path.name, str(exc)))
            log.debug("Не удалось прочитать %s: %s", map_path.name, exc)
            continue

        (version,) = struct.unpack_from("<I", head, 0)
        versions[version] += 1
        if len(examples[version]) < 3:
            examples[version].append(map_path.name)

        log.debug(
            "%-45s version=0x%02X head=%s",
            map_path.name,
            version,
            head[:16].hex(" "),
        )

        if version == 0x20:
            # У HotA сразу за версией идёт собственное поле; предположительно
            # подверсия формата. Проверяем это гипотезой, а не утверждением.
            (subversion,) = struct.unpack_from("<I", head, 4)
            hota_subversions[subversion] += 1

    log.info("")
    log.info("=== Версии формата ===")
    for version, count in versions.most_common():
        name = KNOWN_VERSIONS.get(version, "НЕИЗВЕСТНАЯ")
        log.info("  0x%02X  %-30s %3d карт", version, name, count)
        log.info("        примеры: %s", ", ".join(examples[version]))

    if hota_subversions:
        log.info("")
        log.info("=== Поле сразу за версией у HotA-карт (гипотеза: подверсия) ===")
        for subversion, count in sorted(hota_subversions.items()):
            log.info("  %d — %d карт", subversion, count)

    if broken:
        log.info("")
        log.warning("Не удалось прочитать: %d", len(broken))
        for name, reason in broken:
            log.warning("  %s — %s", name, reason)

    log.info("")
    log.info("Подробный лог: %s", log_path)


if __name__ == "__main__":
    main()
