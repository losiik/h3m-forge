"""Разбор заголовков всех карт из поставки + round-trip заголовка.

Первая настоящая проверка проекта. Для каждой карты:

1. заголовок разбирается;
2. записывается обратно;
3. результат сравнивается с исходными байтами побайтово.

Третий шаг важнее первых двух. Разобрать заголовок «без ошибок» легко: если
неправильно понять поле, парсер всё равно что-то прочитает и не упадёт. А вот
собрать обратно те же самые байты, неправильно поняв поле, невозможно.

Запуск:
    python tools/scan_headers.py
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from h3m import paths
from h3m.container import read_map_bytes
from h3m.header import MapHeader, read_header, write_header
from h3m.logging_setup import setup_logging
from h3m.stream import BinaryReader, BinaryWriter

log = logging.getLogger("scan_headers")


@dataclass(slots=True)
class Failure:
    name: str
    stage: str
    detail: str


def first_difference(left: bytes, right: bytes) -> int:
    """Смещение первого расхождения, либо -1 если совпадают."""
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    if len(left) != len(right):
        return min(len(left), len(right))
    return -1


def check_map(path: Path) -> tuple[MapHeader | None, Failure | None]:
    try:
        data = read_map_bytes(path)
    except OSError as exc:
        return None, Failure(path.name, "распаковка", str(exc))

    reader = BinaryReader(data)
    try:
        header = read_header(reader)
    except Exception as exc:  # noqa: BLE001 — на этом этапе интересна любая поломка
        return None, Failure(path.name, "разбор", f"{type(exc).__name__}: {exc}")

    header_length = reader.pos

    writer = BinaryWriter()
    try:
        write_header(writer, header)
    except Exception as exc:  # noqa: BLE001
        return header, Failure(path.name, "запись", f"{type(exc).__name__}: {exc}")

    rebuilt = writer.getvalue()
    original = data[:header_length]

    if len(rebuilt) != len(original):
        return header, Failure(
            path.name,
            "round-trip",
            f"длина {len(rebuilt)} вместо {len(original)}",
        )

    diff = first_difference(original, rebuilt)
    if diff >= 0:
        return header, Failure(
            path.name,
            "round-trip",
            f"расхождение на байте {diff}: "
            f"{original[diff]:#04x} -> {rebuilt[diff]:#04x}",
        )

    return header, None


def main() -> None:
    log_path = setup_logging("scan_headers")

    maps = list(paths.iter_maps())
    log.info("Карт к разбору: %d", len(maps))

    by_format: Counter[str] = Counter()
    ok_by_format: Counter[str] = Counter()
    failures: list[Failure] = []
    sizes: Counter[int] = Counter()
    hota_versions: Counter[str] = Counter()

    for map_path in maps:
        header, failure = check_map(map_path)

        if header is not None:
            key = header.format.name
            by_format[key] += 1
            sizes[header.size] += 1
            if header.hota:
                hota_versions[header.hota.version_string] += 1
            log.debug("%-45s %s", map_path.name, header)

        if failure is None:
            if header is not None:
                ok_by_format[header.format.name] += 1
        else:
            failures.append(failure)
            log.debug(
                "ОШИБКА %-40s [%s] %s", failure.name, failure.stage, failure.detail
            )

    total = len(maps)
    ok = total - len(failures)

    log.info("")
    log.info("=== Round-trip заголовка ===")
    log.info("  успешно: %d из %d", ok, total)
    for format_name, count in by_format.most_common():
        log.info(
            "    %-5s %3d из %3d", format_name, ok_by_format[format_name], count
        )

    log.info("")
    log.info("=== Размеры карт ===")
    for size, count in sorted(sizes.items()):
        log.info("    %3dx%-3d %3d карт", size, size, count)

    if hota_versions:
        log.info("")
        log.info("=== Версии HotA в заголовках ===")
        for version, count in sorted(hota_versions.items()):
            log.info("    %-8s %3d карт", version, count)

    if failures:
        log.info("")
        log.warning("=== Провалы: %d ===", len(failures))
        by_stage: Counter[str] = Counter(f.stage for f in failures)
        for stage, count in by_stage.most_common():
            log.warning("  этап «%s»: %d", stage, count)
        for failure in failures[:20]:
            log.warning("    %-40s [%s] %s", failure.name, failure.stage, failure.detail)
        if len(failures) > 20:
            log.warning("    ... ещё %d", len(failures) - 20)

    log.info("")
    log.info("Подробный лог: %s", log_path)


if __name__ == "__main__":
    main()
