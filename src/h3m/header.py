"""Заголовок карты: версия формата, размер, название, описание, сложность.

Однобайтовые флаги хранятся как ``int``, а не ``bool``, намеренно. В реальных
файлах встречаются значения вроде 2 там, где по смыслу ожидается 0 или 1;
приведение к bool потеряло бы исходное значение и сломало бы побайтовую
сборку. Задача ридера — воспроизвести файл, а не привести его в порядок.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from h3m.format import MapFeatures, MapFormat, features_for
from h3m.stream import BinaryReader, BinaryWriter, decode

log = logging.getLogger(__name__)


@dataclass(slots=True)
class HotaHeader:
    """HotA-специфичные поля, вклинённые между версией и общим заголовком.

    Порядок полей в файле не совпадает с порядком, в котором возможности
    появлялись в HotA: тройка версии (появилась в подверсии 8) лежит первой,
    до флагов из подверсии 1. Проверено на картах HotA 1.8.0.
    """

    level: int
    """Подверсия формата HotA — поле сразу за версией."""

    version_major: int = 0
    version_minor: int = 0
    version_patch: int = 0

    is_mirror_map: int = 0
    is_arena_map: int = 0

    terrain_types_count: int = 0
    town_types_count: int = 0
    allowed_difficulties_mask: int = 0

    can_hire_defeated_heroes: int = 0
    force_matching_version: int = 0
    unknown_i32: int = 0

    @property
    def version_string(self) -> str:
        return f"{self.version_major}.{self.version_minor}.{self.version_patch}"


@dataclass(slots=True)
class MapHeader:
    """Общий заголовок карты."""

    format: MapFormat
    features: MapFeatures

    any_players: int
    size: int
    two_levels: int

    name: bytes
    description: bytes

    difficulty: int
    level_limit: int = 0
    """Ограничение уровня героев. Отсутствует в RoE, там всегда 0."""

    hota: HotaHeader | None = None

    unknown_version: int | None = field(default=None)
    """Заполняется, если поле версии не совпало ни с одним известным значением."""

    # --- удобства для показа человеку -----------------------------------

    @property
    def name_text(self) -> str:
        return decode(self.name)

    @property
    def description_text(self) -> str:
        return decode(self.description)

    @property
    def levels(self) -> int:
        return 2 if self.two_levels else 1

    @property
    def tile_count(self) -> int:
        return self.size * self.size * self.levels

    def __str__(self) -> str:
        parts = [f"{self.format.name} {self.size}x{self.size}"]
        if self.two_levels:
            parts.append("+подземелье")
        if self.hota:
            parts.append(f"HotA {self.hota.version_string} (подверсия {self.hota.level})")
        parts.append(f"«{self.name_text}»")
        return " ".join(parts)


def read_header(reader: BinaryReader) -> MapHeader:
    """Разобрать заголовок карты из начала потока."""
    raw_version = reader.u32()
    try:
        format_ = MapFormat(raw_version)
    except ValueError as exc:
        raise ValueError(
            f"неизвестная версия формата 0x{raw_version:02X} по смещению 0"
        ) from exc

    hota: HotaHeader | None = None
    hota_level = 0

    if format_ is MapFormat.HOTA:
        hota_level = reader.u32()
        hota = HotaHeader(level=hota_level)

    features = features_for(format_, hota_level)

    if hota is not None:
        _read_hota_block(reader, hota, features)

    any_players = reader.u8()
    size = reader.u32()
    two_levels = reader.u8()
    name = reader.string()
    description = reader.string()
    difficulty = reader.u8()
    level_limit = reader.u8() if features.has_level_limit else 0

    header = MapHeader(
        format=format_,
        features=features,
        any_players=any_players,
        size=size,
        two_levels=two_levels,
        name=name,
        description=description,
        difficulty=difficulty,
        level_limit=level_limit,
        hota=hota,
    )
    log.debug("Заголовок разобран: %s (позиция %d)", header, reader.pos)
    return header


def _read_hota_block(reader: BinaryReader, hota: HotaHeader, features: MapFeatures) -> None:
    """Прочитать HotA-специфичные поля. Порядок проверен на реальных картах."""
    if features.hota_has_version_triplet:
        hota.version_major = reader.u32()
        hota.version_minor = reader.u32()
        hota.version_patch = reader.u32()

    if features.hota_has_mirror_arena:
        hota.is_mirror_map = reader.u8()
        hota.is_arena_map = reader.u8()

    if features.hota_has_terrain_count:
        hota.terrain_types_count = reader.u32()

    if features.hota_has_town_count:
        hota.town_types_count = reader.u32()
        hota.allowed_difficulties_mask = reader.i8()

    if features.hota_has_defeated_heroes:
        hota.can_hire_defeated_heroes = reader.u8()

    if features.hota_has_version_triplet:
        hota.force_matching_version = reader.u8()

    if features.hota_has_unknown_i32:
        hota.unknown_i32 = reader.i32()


def write_header(writer: BinaryWriter, header: MapHeader) -> None:
    """Записать заголовок обратно. Зеркало read_header."""
    writer.u32(int(header.format))

    features = header.features
    if header.hota is not None:
        writer.u32(header.hota.level)
        _write_hota_block(writer, header.hota, features)

    writer.u8(header.any_players)
    writer.u32(header.size)
    writer.u8(header.two_levels)
    writer.string(header.name)
    writer.string(header.description)
    writer.u8(header.difficulty)
    if features.has_level_limit:
        writer.u8(header.level_limit)


def _write_hota_block(writer: BinaryWriter, hota: HotaHeader, features: MapFeatures) -> None:
    if features.hota_has_version_triplet:
        writer.u32(hota.version_major)
        writer.u32(hota.version_minor)
        writer.u32(hota.version_patch)

    if features.hota_has_mirror_arena:
        writer.u8(hota.is_mirror_map)
        writer.u8(hota.is_arena_map)

    if features.hota_has_terrain_count:
        writer.u32(hota.terrain_types_count)

    if features.hota_has_town_count:
        writer.u32(hota.town_types_count)
        writer.i8(hota.allowed_difficulties_mask)

    if features.hota_has_defeated_heroes:
        writer.u8(hota.can_hire_defeated_heroes)

    if features.hota_has_version_triplet:
        writer.u8(hota.force_matching_version)

    if features.hota_has_unknown_i32:
        writer.i32(hota.unknown_i32)
