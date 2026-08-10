"""Каталог шаблонов объектов, собранный из настоящих карт.

Зачем: при генерации карты каждому объекту нужна запись шаблона — имя файла
спрайта, маски проходимости и посещаемости, допустимые рельефы. Сочинить их
нельзя: неверное имя спрайта или неподходящая маска дают карту, которая в
лучшем случае выглядит сломанной, в худшем роняет редактор.

Решение — не сочинять. В поставке лежит 221 карта, и в них встречаются тысячи
шаблонов, каждый из которых заведомо корректен, потому что сделан авторами
игры. Скрипт собирает их в каталог, из которого генератор потом берёт готовое.

Каталог пишется в reference/ и в репозиторий не попадает: это производная от
данных игры.

Запуск:
    python tools/build_template_catalog.py
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field

from h3m import mapfile, paths
from h3m.logging_setup import setup_logging
from h3m.objects import ObjectTemplate

log = logging.getLogger("template_catalog")


@dataclass(slots=True)
class CatalogEntry:
    """Уникальный шаблон и сведения о том, где он встречается."""

    template: ObjectTemplate
    occurrences: int = 0
    maps: set[str] = field(default_factory=set)


def template_key(template: ObjectTemplate) -> tuple:
    """Ключ уникальности: всё, что влияет на поведение и вид."""
    return (
        template.animation_file,
        template.block_mask,
        template.visit_mask,
        template.terrain_mask,
        template.object_id,
        template.object_subid,
        template.object_type,
        template.print_priority,
    )


def main() -> None:
    log_path = setup_logging("template_catalog")

    catalog: dict[tuple, CatalogEntry] = {}
    scanned = skipped = 0

    for map_path in paths.iter_maps():
        parsed = mapfile.load(map_path)
        if parsed.object_templates is None:
            skipped += 1
            continue

        scanned += 1
        for template in parsed.object_templates:
            key = template_key(template)
            entry = catalog.get(key)
            if entry is None:
                entry = catalog[key] = CatalogEntry(template=template)
            entry.occurrences += 1
            entry.maps.add(map_path.name)

    log.info("Просмотрено карт: %d (пропущено %d)", scanned, skipped)
    log.info("Уникальных шаблонов: %d", len(catalog))

    by_object: Counter[int] = Counter(
        entry.template.object_id for entry in catalog.values()
    )
    log.info("Разных типов объектов: %d", len(by_object))

    log.info("")
    log.info("Самые распространённые шаблоны:")
    popular = sorted(catalog.values(), key=lambda e: -e.occurrences)
    for entry in popular[:15]:
        log.info(
            "  %-16s id=%-4d subid=%-4d встречается %4d раз в %3d картах",
            entry.template.animation_text,
            entry.template.object_id,
            entry.template.object_subid,
            entry.occurrences,
            len(entry.maps),
        )

    payload = [
        {
            "animation": entry.template.animation_text,
            "block_mask": entry.template.block_mask.hex(),
            "visit_mask": entry.template.visit_mask.hex(),
            "unknown": entry.template.unknown,
            "terrain_mask": entry.template.terrain_mask,
            "id": entry.template.object_id,
            "subid": entry.template.object_subid,
            "type": entry.template.object_type,
            "print_priority": entry.template.print_priority,
            "trailing": entry.template.trailing.hex(),
            "occurrences": entry.occurrences,
            "maps": len(entry.maps),
        }
        for entry in popular
    ]

    out_path = paths.reference_dir() / "object_templates.json"
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    log.info("")
    log.info("Каталог: %s (%d записей)", out_path, len(payload))
    log.info("Подробный лог: %s", log_path)


if __name__ == "__main__":
    main()
