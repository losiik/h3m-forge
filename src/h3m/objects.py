"""Шаблоны объектов — описания того, чем объект выглядит и как занимает место.

Самый важный блок для генерации карт. Каждый шаблон связывает тип объекта с
файлом спрайта и двумя масками на сетке 8x6: какие клетки объект перекрывает
и с каких его можно посетить.

Именно поэтому блок разбирается раньше самих объектов: сочинять имена спрайтов
и маски проходимости с нуля — верный способ получить карту, которая уронит
редактор. Правильный путь — брать шаблоны из настоящих карт и переиспользовать,
и для этого их надо уметь читать.

Маски хранятся байтами в том виде, в каком лежат в файле. Раскладка нетривиальна:
строки идут снизу вверх, столбцы справа налево, а бит проходимости
**инвертирован** — ноль означает «занято». Разворачивать это в удобный вид —
задача представления, а не хранения.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from h3m.stream import BinaryReader, BinaryWriter, decode

log = logging.getLogger(__name__)

MASK_ROWS = 6
MASK_COLUMNS = 8
TRAILING_BYTES = 16
"""Хвост шаблона, назначение которого в VCMI просто пропускается."""


@dataclass(slots=True)
class ObjectTemplate:
    """Описание внешнего вида и занимаемого места для типа объекта."""

    animation_file: bytes
    """Имя файла спрайта, например b'AVXcrs00.def'."""

    block_mask: bytes
    """6 байт: бит равен нулю там, где клетка заблокирована."""

    visit_mask: bytes
    """6 байт: бит равен единице там, где клетку можно посетить."""

    unknown: int
    """Двухбайтовое поле, назначение которого не установлено."""

    terrain_mask: int
    """Битовая маска рельефов, на которых объект допустим."""

    object_id: int
    object_subid: int
    object_type: int
    print_priority: int

    trailing: bytes
    """16 байт в конце записи."""

    @property
    def animation_text(self) -> str:
        return decode(self.animation_file)

    def blocked_cells(self) -> list[tuple[int, int]]:
        """Клетки, которые объект перекрывает, в координатах относительно якоря.

        Разворачивает хранимую раскладку: строки снизу вверх, столбцы справа
        налево, бит проходимости инвертирован.
        """
        cells: list[tuple[int, int]] = []
        for row in range(MASK_ROWS):
            for column in range(MASK_COLUMNS):
                if not (self.block_mask[row] >> column) & 1:
                    cells.append((MASK_COLUMNS - 1 - column, MASK_ROWS - 1 - row))
        return cells

    def visitable_cells(self) -> list[tuple[int, int]]:
        """Клетки, с которых объект можно посетить."""
        cells: list[tuple[int, int]] = []
        for row in range(MASK_ROWS):
            for column in range(MASK_COLUMNS):
                if (self.visit_mask[row] >> column) & 1:
                    cells.append((MASK_COLUMNS - 1 - column, MASK_ROWS - 1 - row))
        return cells

    def allows_terrain(self, terrain: int) -> bool:
        return bool((self.terrain_mask >> terrain) & 1)

    def __str__(self) -> str:
        return (
            f"{self.animation_text} "
            f"(id={self.object_id}, subid={self.object_subid}, "
            f"тип={self.object_type})"
        )


def read_object_templates(reader: BinaryReader) -> list[ObjectTemplate]:
    """Прочитать таблицу шаблонов объектов."""
    count = reader.u32()
    if count > 10_000:
        raise ValueError(f"неправдоподобное число шаблонов объектов: {count}")

    templates = [
        ObjectTemplate(
            animation_file=reader.string(),
            block_mask=reader.bytes_(MASK_ROWS),
            visit_mask=reader.bytes_(MASK_ROWS),
            unknown=reader.u16(),
            terrain_mask=reader.u16(),
            object_id=reader.u32(),
            object_subid=reader.u32(),
            object_type=reader.u8(),
            print_priority=reader.u8(),
            trailing=reader.bytes_(TRAILING_BYTES),
        )
        for _ in range(count)
    ]

    log.debug("Шаблонов объектов: %d", len(templates))
    return templates


def write_object_templates(
    writer: BinaryWriter, templates: list[ObjectTemplate]
) -> None:
    """Зеркало read_object_templates."""
    writer.u32(len(templates))
    for template in templates:
        writer.string(template.animation_file)
        writer.bytes_(template.block_mask)
        writer.bytes_(template.visit_mask)
        writer.u16(template.unknown)
        writer.u16(template.terrain_mask)
        writer.u32(template.object_id)
        writer.u32(template.object_subid)
        writer.u8(template.object_type)
        writer.u8(template.print_priority)
        writer.bytes_(template.trailing)
