"""Рельеф — массив тайлов.

Самый простой блок формата и одновременно самый крупный: на карте 36x36 с
подземельем это 18 144 байта, а на 252x252 — почти девять мегабайт. Никакой
переменной длины, никаких версионных отличий: ровно семь байт на тайл,
порядок обхода [z][y][x].

Байты хранятся одним куском, а доступ к отдельному тайлу даётся через
представление. Так и память не тратится на десятки тысяч мелких объектов,
и запись обратно тривиально точна.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum

from h3m.stream import BinaryReader, BinaryWriter

log = logging.getLogger(__name__)

TILE_SIZE = 7
"""Байт на тайл: рельеф, вид, река, направление реки, дорога, её направление, флаги."""


class Terrain(IntEnum):
    """Типы рельефа. Последние два добавлены HotA."""

    DIRT = 0
    SAND = 1
    GRASS = 2
    SNOW = 3
    SWAMP = 4
    ROUGH = 5
    SUBTERRANEAN = 6
    LAVA = 7
    WATER = 8
    ROCK = 9
    HIGHLANDS = 10
    WASTELAND = 11


@dataclass(frozen=True, slots=True)
class Tile:
    """Один тайл карты."""

    terrain: int
    terrain_view: int
    river: int
    river_dir: int
    road: int
    road_dir: int
    flags: int

    @property
    def is_water(self) -> bool:
        return self.terrain == Terrain.WATER

    @property
    def is_passable(self) -> bool:
        """Скалы непроходимы всегда; вода — только для кораблей."""
        return self.terrain != Terrain.ROCK


@dataclass(slots=True)
class TerrainMap:
    """Массив тайлов карты."""

    data: bytes
    size: int
    levels: int

    @property
    def tile_count(self) -> int:
        return self.size * self.size * self.levels

    def offset_of(self, x: int, y: int, z: int = 0) -> int:
        """Смещение тайла в массиве. Порядок обхода [z][y][x]."""
        if not (0 <= x < self.size and 0 <= y < self.size and 0 <= z < self.levels):
            raise IndexError(f"тайл ({x}, {y}, {z}) вне карты {self.size}x{self.size}")
        return ((z * self.size + y) * self.size + x) * TILE_SIZE

    def tile(self, x: int, y: int, z: int = 0) -> Tile:
        """Прочитать тайл."""
        start = self.offset_of(x, y, z)
        raw = self.data[start : start + TILE_SIZE]
        return Tile(*raw)

    def terrain_histogram(self) -> dict[int, int]:
        """Сколько тайлов каждого типа рельефа — для проверок и отчётов."""
        counts: dict[int, int] = {}
        for offset in range(0, len(self.data), TILE_SIZE):
            key = self.data[offset]
            counts[key] = counts.get(key, 0) + 1
        return counts


def read_terrain(reader: BinaryReader, size: int, levels: int) -> TerrainMap:
    """Прочитать массив тайлов."""
    expected = size * size * levels * TILE_SIZE
    data = reader.bytes_(expected)
    log.debug("Рельеф: %d тайлов, %d байт", size * size * levels, expected)
    return TerrainMap(data=data, size=size, levels=levels)


def write_terrain(writer: BinaryWriter, terrain: TerrainMap) -> None:
    """Записать массив тайлов обратно."""
    writer.bytes_(terrain.data)
