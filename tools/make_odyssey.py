"""Собрать карту «Одиссея» и проверить её собственным ридером.

Проверка та же, что и для пустой карты: разбор до последнего байта с хвостом
в 124 байта и побайтовая пересборка. Она доказывает, что файл устроен как
настоящие карты, но не доказывает, что игра примет каждый объект — это
показывает только редактор.

Запуск:
    python tools/make_odyssey.py
"""

from __future__ import annotations

import logging
from collections import Counter

from h3m import mapfile, paths
from h3m.logging_setup import setup_logging
from h3m.objtypes import Obj
from odyssey import build, design

log = logging.getLogger("make_odyssey")

EXPECTED_TRAILING = 124


def type_name(object_id: int) -> str:
    try:
        return Obj(object_id).name
    except ValueError:
        return f"id={object_id}"


def verify(data: bytes) -> bool:
    parsed = mapfile.parse(data)
    problems: list[str] = []

    if parsed.stopped_at:
        problems.append(f"разбор остановлен: {parsed.stopped_at}")
    if parsed.tail:
        problems.append(f"осталось {len(parsed.tail)} неразобранных байт")
    if parsed.events is None:
        problems.append("блок событий не разобран")
    elif len(parsed.events.trailing) != EXPECTED_TRAILING:
        problems.append(f"хвост {len(parsed.events.trailing)} вместо {EXPECTED_TRAILING}")
    if mapfile.serialize(parsed) != data:
        problems.append("round-trip не сошёлся")

    for problem in problems:
        log.error("  %s", problem)
    return not problems


def main() -> None:
    log_path = setup_logging("make_odyssey")

    parsed = build.build_map()
    data = mapfile.serialize(parsed)

    log.info("Карта «%s»: %d байт распакованных", design.MAP_NAME, len(data))
    log.info("  %s", parsed.header)
    log.info("  эпизодов %d, засад %d", len(design.ROUTE), len(design.POSEIDON_AMBUSHES))

    counts: Counter[str] = Counter(
        type_name(instance.object_id) for instance in (parsed.objects or [])
    )
    log.info("  объектов %d:", sum(counts.values()))
    for name, count in counts.most_common():
        log.info("      %-16s %d", name, count)

    log.info("")
    log.info("Проверка собственным ридером:")
    ok = verify(data)
    if ok:
        log.info("  разобрана до конца, round-trip сошёлся")

    out_path = paths.out_dir() / "odyssey.h3m"
    mapfile.save(out_path, parsed)
    log.info("")
    log.info("Записано: %s (%d байт)", out_path, out_path.stat().st_size)
    log.info("Итог: %s", "готово" if ok else "ЕСТЬ ПРОБЛЕМЫ")
    log.info("Подробный лог: %s", log_path)


if __name__ == "__main__":
    main()
