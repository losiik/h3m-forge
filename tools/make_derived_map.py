"""Карта, полученная из настоящей вычитанием, а не построенная с нуля.

Нужна для разделения причин, когда сгенерированная карта не открывается.

Берём реальную карту из поставки и удаляем из неё объекты, оставив заголовок,
настройки, маски и рельеф нетронутыми. Всё, что мы могли выдумать неправильно,
здесь взято у авторов игры; наша только операция удаления.

Дальше проверка на один бит информации:

* открывается, а сгенерированная с нуля — нет → виноваты наши собственные
  значения в заголовке, масках или рельефе;
* не открывается тоже → дело в самом отсутствии объектов, и пустая карта
  редактору не годится в принципе.

Запуск:
    python tools/make_derived_map.py
"""

from __future__ import annotations

import logging

from h3m import mapfile, paths
from h3m.container import read_map_bytes
from h3m.format import MapFormat
from h3m.logging_setup import setup_logging

log = logging.getLogger("make_derived")


def pick_source() -> tuple[str, mapfile.H3Map]:
    """Найти небольшую карту SoD, разобранную до конца."""
    for map_path in paths.iter_maps():
        parsed = mapfile.parse(read_map_bytes(map_path))
        if (
            parsed.header.format is MapFormat.SOD
            and parsed.header.size == 36
            and parsed.header.levels == 1
            and parsed.events is not None
        ):
            return map_path.name, parsed
    raise RuntimeError("подходящей карты SoD 36x36 не нашлось")


def main() -> None:
    log_path = setup_logging("make_derived")

    name, parsed = pick_source()
    log.info("Источник: %s — %s", name, parsed.header)
    log.info(
        "  было: шаблонов %d, объектов %d",
        len(parsed.object_templates or []),
        len(parsed.objects or []),
    )

    parsed.header.name = "Вычитанием из настоящей".encode("cp1251")
    parsed.header.description = (
        "Настоящая карта, из которой удалены все объекты.".encode("cp1251")
    )
    parsed.object_templates = []
    parsed.objects = []

    # Стартовые города удалены вместе с объектами — снимаем и ссылки на них,
    # иначе игроки указывают на пустые координаты.
    for player in parsed.players:
        if player.is_playable:
            player.has_main_town = 0
            player.main_town_pos = (0, 0, 0)

    out_path = paths.out_dir() / "derived.h3m"
    mapfile.save(out_path, parsed)

    check = mapfile.parse(mapfile.serialize(parsed))
    log.info(
        "  стало: шаблонов %d, объектов %d, разобрана до конца: %s",
        len(check.object_templates or []),
        len(check.objects or []),
        check.events is not None and not check.tail,
    )
    log.info("")
    log.info("Записано: %s (%d байт)", out_path, out_path.stat().st_size)
    log.info("Подробный лог: %s", log_path)


if __name__ == "__main__":
    main()
