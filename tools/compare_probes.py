"""Измерить длину записи объекта по эталонным картам из редактора.

Все прежние измерения были косвенными: длина выводилась из того, где
предположительно начинается следующий объект. В нулевых областях этот приём
врёт — любая позиция там похожа на заголовок, — и трижды за день выдавал
убедительные, но ложные результаты.

Здесь измерение прямое. Две карты, отличающиеся ровно одним объектом, дают
разницу в размере, равную одной записи плюс двенадцать байт заголовка. Никаких
предположений: ответ получается вычитанием.

Карты делает редактор HotA, поэтому их структура канонична по определению.

Что нужно положить в out/ (инструкция в диалоге):
    probe_1monster.h3m   — пустая карта 36x36 с одним случайным монстром
    probe_2monsters.h3m  — то же, но с двумя
    probe_town.h3m       — то же, но с одним случайным городом

Запуск:
    python tools/compare_probes.py
"""

from __future__ import annotations

import logging
from dataclasses import replace

from h3m import mapfile, paths
from h3m.container import read_map_bytes
from h3m.logging_setup import setup_logging
from h3m.objtypes import Obj
from h3m.stream import BinaryReader

log = logging.getLogger("compare_probes")

OBJECT_HEADER = 12
"""Координаты (3), номер шаблона (4) и пять нулевых байт."""

FILE_TAIL = 128
"""Ноль глобальных событий (4 байта) плюс 124 нуля в конце файла."""


def find_probe(name: str):
    """Найти эталонную карту там, где её мог сохранить редактор.

    Редактор HotA по умолчанию пишет в папку карт игры, и заставлять человека
    воевать с диалогом сохранения ради нашего удобства незачем.
    """
    candidates = [paths.out_dir() / name]
    try:
        candidates.append(paths.maps_dir() / name)
    except paths.GameNotFoundError:
        pass
    return next((path for path in candidates if path.exists()), None)


def describe(name: str) -> tuple[bytes, mapfile.H3Map] | None:
    path = find_probe(name)
    if path is None:
        log.warning("нет файла %s (искал в out/ и в папке карт игры)", name)
        return None

    data = read_map_bytes(path)
    parsed = mapfile.parse(data)
    # Проверять надо длину хвоста, а не сам факт разбора: блок событий
    # «успешно» прочитается почти из любого мусора, потому что остаток файла
    # он просто забирает целиком. Именно так эталонная карта с городом
    # объявила себя разобранной, имея хвост в 170 байт вместо 124.
    complete = (
        parsed.events is not None
        and not parsed.tail
        and len(parsed.events.trailing) == FILE_TAIL - 4
    )
    log.info(
        "%-22s %6d байт, %s, объектов %s, разобрана %s",
        name,
        len(data),
        parsed.header,
        len(parsed.objects) if parsed.objects is not None else "не разобраны",
        "целиком" if complete else f"частично ({parsed.stopped_at})",
    )
    return data, parsed


def objects_start(parsed: mapfile.H3Map) -> int:
    """Смещение, с которого начинается список объектов.

    Считаем сборкой: записываем всё, что идёт до объектов, и берём длину.
    Вычислять это через «хвост» нельзя — у полностью разобранной карты хвоста
    нет, и прежняя версия скрипта на таких картах падала.
    """
    prefix = replace(parsed, objects=None, events=None, tail=b"")
    return len(mapfile.serialize(prefix))


def measure_single_object(data: bytes, parsed: mapfile.H3Map) -> int | None:
    """Длина начинки единственного объекта карты.

    Объектов ровно один, значит его запись зажата между известными границами:
    слева — счётчик объектов, справа — блок глобальных событий, который на
    таких картах пуст и занимает вместе с хвостом ровно 128 байт.
    """
    if parsed.object_templates is None:
        log.error("  таблица шаблонов не разобрана")
        return None

    reader = BinaryReader(data)
    reader.pos = objects_start(parsed)
    count = reader.u32()
    if count != 1:
        log.error("  ожидался один объект, а их %d", count)
        return None

    payload_start = reader.pos + OBJECT_HEADER
    return (len(data) - FILE_TAIL) - payload_start


def main() -> None:
    log_path = setup_logging("compare_probes")

    log.info("=== Эталонные карты из редактора ===")
    one = describe("probe_1monster.h3m")
    two = describe("probe_2monsters.h3m")
    town = describe("probe_town.h3m")

    if one and two:
        log.info("")
        log.info("=== Запись монстра ===")
        difference = len(two[0]) - len(one[0])
        log.info("  разница размеров: %d байт", difference)
        log.info(
            "  длина записи монстра: %d байт (разница минус %d байт заголовка)",
            difference - OBJECT_HEADER,
            OBJECT_HEADER,
        )

        measured = measure_single_object(*one)
        if measured is not None:
            log.info("  проверка по одиночной карте: %d байт", measured)

        expected = _our_length(one[1], Obj.RANDOM_MONSTER)
        if expected is not None:
            log.info("  наша раскладка даёт: %d байт", expected)

    if town:
        log.info("")
        log.info("=== Запись города ===")
        measured = measure_single_object(*town)
        if measured is not None:
            log.info("  длина записи: %d байт", measured)
        expected = _our_length(town[1], Obj.RANDOM_TOWN)
        if expected is not None:
            log.info("  наша раскладка даёт: %d байт", expected)

    log.info("")
    log.info("Подробный лог: %s", log_path)


def _our_length(parsed: mapfile.H3Map, object_id: int) -> int | None:
    """Сколько байт насчитала бы наша раскладка для единственного объекта."""
    if parsed.objects:
        for instance in parsed.objects:
            if instance.object_id == object_id:
                return len(instance.payload)
    return None


if __name__ == "__main__":
    main()
