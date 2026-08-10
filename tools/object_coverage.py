"""Что мешает разобрать объекты: отчёт по типам.

Разбор объектов последовательный, поэтому первая же ошибка останавливает всю
карту. Скрипт доходит до первой остановки и разделяет два принципиально разных
случая:

* **не реализовано** — тип с собственной начинкой, длину которой мы ещё не
  установили. Честная остановка, не ошибка;
* **неверная раскладка** — начинка прочитана, но не сошлась: либо чтение
  вылетело за границы, либо следующий объект оказался не на месте. Вот это
  ошибка, и виноват в ней конкретный тип.

Разделение важно: первое лечится работой, второе — исправлением.

Итоговые гистограммы задают порядок работ: реализовывать типы имеет смысл в
порядке того, сколько карт они разблокируют.

Запуск:
    python tools/object_coverage.py
"""

from __future__ import annotations

import logging
from collections import Counter

from h3m import paths
from h3m.container import read_map_bytes
from h3m.header import read_header
from h3m.instances import DriftError, PayloadError, UnknownObjectError, read_objects
from h3m.logging_setup import setup_logging
from h3m.mapfile import parse
from h3m.objtypes import Obj
from h3m.stream import BinaryReader

log = logging.getLogger("object_coverage")


def type_name(object_id: int) -> str:
    try:
        return Obj(object_id).name
    except ValueError:
        return f"id={object_id}"


def main() -> None:
    log_path = setup_logging("object_coverage")

    unknown: Counter[str] = Counter()
    broken: Counter[str] = Counter()
    fully_parsed = 0
    parsed_objects = 0
    skipped = 0

    for map_path in paths.iter_maps():
        parsed = parse(read_map_bytes(map_path))

        if parsed.object_templates is None:
            skipped += 1
            continue

        if parsed.objects is not None:
            fully_parsed += 1
            parsed_objects += len(parsed.objects)
            continue

        # Повторяем разбор объектов, чтобы узнать причину остановки.
        reader = BinaryReader(read_map_bytes(map_path))
        read_header(reader)
        reader.pos = parsed.total_size - len(parsed.tail)
        format_name = parsed.header.format.name

        try:
            read_objects(reader, parsed.object_templates, parsed.header.features)
        except UnknownObjectError as exc:
            unknown[type_name(exc.object_id)] += 1
            log.debug("%-45s ждёт %s", map_path.name, type_name(exc.object_id))
        except PayloadError as exc:
            broken[f"{type_name(exc.object_id)} / {format_name}"] += 1
            log.debug("%-45s %s", map_path.name, exc)
        except DriftError as exc:
            previous = type_name(exc.previous.object_id) if exc.previous else "начало"
            broken[f"после {previous} / {format_name}"] += 1
            log.debug("%-45s %s", map_path.name, exc)

    total = fully_parsed + len(list(unknown.elements())) + len(list(broken.elements()))

    log.info("Карт с полностью разобранными объектами: %d из %d", fully_parsed, total)
    log.info("Объектов разобрано:                      %d", parsed_objects)
    if skipped:
        log.info("Не дошли до объектов:                    %d", skipped)

    if broken:
        log.info("")
        log.warning("=== Неверная раскладка (это ошибки) ===")
        for key, count in broken.most_common(20):
            log.warning("  %-36s %3d карт", key, count)

    if unknown:
        log.info("")
        log.info("=== Ещё не реализовано (порядок работ) ===")
        for key, count in unknown.most_common(20):
            log.info("  %-24s %3d карт", key, count)

    log.info("")
    log.info("Подробный лог: %s", log_path)


if __name__ == "__main__":
    main()
