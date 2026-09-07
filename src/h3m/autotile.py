"""Terrain appearances learned from local game maps, including their flips.

Never infer a border frame from its frequency alone. Index it by the full
3x3 terrain neighbourhood, and refuse layouts for which no example exists.
Neighbour categories follow the native/dirt/sand transition model documented
at https://github.com/vcmi/vcmi/blob/develop/config/terrainViewPatterns.json.
The actual frame numbers and flags come exclusively from the user's maps.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from random import Random

from h3m import mapfile
from h3m.terrain import TILE_SIZE, Terrain, TerrainMap


def neighbourhood(terrain: TerrainMap, x: int, y: int, z: int) -> tuple[int, ...]:
    size = terrain.size
    data = terrain.data
    own = data[((z * size + y) * size + x) * TILE_SIZE]
    result = [own]
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            nx, ny = min(size - 1, max(0, x + dx)), min(size - 1, max(0, y + dy))
            other = data[((z * size + ny) * size + nx) * TILE_SIZE]
            if own == Terrain.SAND or other == own:
                category = 0
            elif other in (Terrain.SAND, Terrain.WATER, Terrain.ROCK):
                category = 2
            elif own in (Terrain.WATER, Terrain.ROCK):
                category = 2
            elif own == Terrain.DIRT:
                category = 0
            else:
                category = 1
            result.append(category)
    return tuple(result)


@dataclass
class TerrainCatalog:
    samples: dict = field(default_factory=lambda: defaultdict(Counter))
    sources: int = 0

    def learn(self, terrain: TerrainMap) -> None:
        for z in range(terrain.levels):
            # Interior examples avoid ambiguous off-map rendering conventions.
            for y in range(1, terrain.size - 1):
                for x in range(1, terrain.size - 1):
                    tile = terrain.tile(x, y, z)
                    key = neighbourhood(terrain, x, y, z)
                    # Bits 0/1 mirror terrain; bit 6 marks coastal terrain.
                    self.samples[key][(tile.terrain_view, tile.flags & 0x43)] += 1
        self.sources += 1

    @classmethod
    def from_maps(cls, files: list[Path]):
        result = cls()
        for path in files:
            parsed = mapfile.load(path)
            if parsed.terrain is not None:
                result.learn(parsed.terrain)
        return result

    def apply(self, terrain: TerrainMap, seed: int = 0) -> None:
        rng = Random(seed)
        data = bytearray(terrain.data)
        missing = []
        for z in range(terrain.levels):
            for y in range(terrain.size):
                for x in range(terrain.size):
                    key = neighbourhood(terrain, x, y, z)
                    choices = self.samples.get(key)
                    if not choices:
                        missing.append((x, y, z, key))
                        continue
                    # The modal frame family excludes rare hand-edited outliers;
                    # retain alternatives with substantial corpus support.
                    peak = max(choices.values())
                    candidates = sorted(k for k, count in choices.items() if count * 4 >= peak)
                    view, flags = rng.choice(candidates)
                    # Rendering categories deliberately merge sand/water/rock,
                    # and dirt/sand may ignore neighbours entirely. A sample's
                    # land-coast bit therefore says nothing about THIS shore.
                    own = terrain.tile(x, y, z).terrain
                    if own not in (Terrain.WATER, Terrain.ROCK):
                        water_nearby = any(
                            0 <= x+dx < terrain.size and 0 <= y+dy < terrain.size
                            and terrain.tile(x+dx, y+dy, z).is_water
                            for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy)
                        flags = (flags & ~0x40) | (0x40 if water_nearby else 0)
                    offset = terrain.offset_of(x, y, z)
                    data[offset + 1] = view
                    data[offset + 6] = (data[offset + 6] & ~0x43) | flags
        if missing:
            raise ValueError(f"No terrain reference for {len(missing)} cells: {missing[:3]}")
        terrain.data = bytes(data)
