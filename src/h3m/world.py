"""Seeded zone-based world generation for HotA, independent of any story.

Connections guarantee walking access, not isolation or mandatory battles.
The first backend builds a surface archipelago joined by broad land bridges.
"""

from collections import Counter, deque
from dataclasses import asdict, dataclass, field
import json
from math import cos, hypot, pi, sin
from random import Random
import struct

from h3m import catalog, hota, mapfile
from h3m.autotile import TerrainCatalog
from h3m.objects import ObjectTemplate
from h3m.objtypes import Obj
from h3m.terrain import Terrain, TerrainMap


@dataclass(frozen=True)
class Zone:
    id: str
    terrain: str = "grass"
    player: int | None = None


@dataclass(frozen=True)
class WorldSpec:
    name: str
    zones: tuple[Zone, ...]
    connections: tuple[tuple[str, str], ...]
    size: int = 72
    seed: int = 0
    decoration_density: float = 0.16

    @classmethod
    def from_dict(cls, value: dict):
        fields = dict(value)
        fields["zones"] = tuple(Zone(**z) for z in fields["zones"])
        fields["connections"] = tuple(tuple(edge) for edge in fields["connections"])
        result = cls(**fields)
        result.validate()
        return result

    def validate(self):
        if type(self.size) is not int or self.size not in (72, 108, 144):
            raise ValueError("world size must be 72, 108 or 144")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ValueError("seed must be an integer")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must not be empty")
        self.name.encode("cp1251")
        if not 2 <= len(self.zones) <= 8:
            raise ValueError("provide 2 to 8 zones")
        ids = [z.id for z in self.zones]
        if any(not isinstance(key, str) or not key for key in ids) or len(set(ids)) != len(ids):
            raise ValueError("zone ids must be nonempty and unique")
        for zone in self.zones:
            if zone.terrain.upper() not in Terrain.__members__ or zone.terrain.upper() in (
                "WATER", "ROCK", "SUBTERRANEAN",
            ):
                raise ValueError(f"unsupported surface terrain: {zone.terrain}")
            if zone.player is not None and (type(zone.player) is not int or zone.player < 0):
                raise ValueError("player must be a nonnegative integer")
        players = sorted(z.player for z in self.zones if z.player is not None)
        if not 2 <= len(players) <= 8 or players != list(range(len(players))):
            raise ValueError("assign each player exactly one zone, numbered 0..N-1 (N >= 2)")
        if not 0 <= self.decoration_density <= 0.4:
            raise ValueError("decoration_density must be between 0 and 0.4")
        adjacency = {key: set() for key in ids}
        edges = set()
        for edge in self.connections:
            if len(edge) != 2 or any(key not in adjacency for key in edge) or edge[0] == edge[1]:
                raise ValueError(f"invalid connection: {edge}")
            canonical = tuple(sorted(edge))
            if canonical in edges:
                raise ValueError(f"duplicate connection: {edge}")
            edges.add(canonical)
            a, b = edge
            adjacency[a].add(b)
            adjacency[b].add(a)
        seen, pending = set(), [ids[0]]
        while pending:
            key = pending.pop()
            if key not in seen:
                seen.add(key)
                pending.extend(adjacency[key] - seen)
        if seen != set(ids):
            raise ValueError("zone graph must be connected")


@dataclass
class Assets:
    """Templates indexed once; scenario payloads are deliberately discarded."""
    templates: dict = field(default_factory=dict)
    decorations: list = field(default_factory=list)
    terrain: TerrainCatalog = field(default_factory=TerrainCatalog)

    @classmethod
    def from_maps(cls, files):
        result = cls()
        seen = set()
        for path in files:
            parsed = mapfile.load(path)
            if parsed.terrain:
                result.terrain.learn(parsed.terrain)
            for template in parsed.object_templates or []:
                key = (template.object_id, template.object_subid)
                variants = result.templates.setdefault(key, [])
                if template not in variants:
                    variants.append(template)
                # Empty payload alone does not make an object scenery.
                # Native scenery types 114..140 have no visitable cells.
                if (114 <= template.object_id <= 140 and template.object_type == 0
                        and not any(template.visit_mask)
                        and template.blocked_cells()
                        and template.animation_file not in seen):
                    result.decorations.append(template)
                    seen.add(template.animation_file)
        result.decorations.sort(key=lambda t: (t.object_id, t.object_subid, t.animation_file))
        return result

    @classmethod
    def cached(cls, files, cache_path):
        signature = [[str(p.resolve()), p.stat().st_size, p.stat().st_mtime_ns] for p in files]
        if cache_path.exists():
            value = json.loads(cache_path.read_text(encoding="utf-8"))
            if value.get("version") == 2 and value.get("signature") == signature:
                result = cls()
                for row in value["templates"]:
                    fields = dict(row)
                    for name in ("animation_file", "block_mask", "visit_mask", "trailing"):
                        fields[name] = bytes.fromhex(fields[name])
                    t = ObjectTemplate(**fields)
                    result.templates.setdefault((t.object_id, t.object_subid), []).append(t)
                for row in value["decorations"]:
                    fields = dict(row)
                    for name in ("animation_file", "block_mask", "visit_mask", "trailing"):
                        fields[name] = bytes.fromhex(fields[name])
                    result.decorations.append(ObjectTemplate(**fields))
                for key, samples in value["terrain"]:
                    result.terrain.samples[tuple(key)] = Counter({(v, f): c for v, f, c in samples})
                result.terrain.sources = value["sources"]
                return result
        result = cls.from_maps(files)
        templates = []
        for group in result.templates.values():
            for template in group:
                templates.append({k: v.hex() if isinstance(v, bytes) else v
                                  for k, v in asdict(template).items()})
        value = dict(version=2, signature=signature, templates=templates,
                     decorations=[{k: v.hex() if isinstance(v, bytes) else v
                                   for k, v in asdict(t).items()} for t in result.decorations],
                     sources=result.terrain.sources,
                     terrain=[[key, [[v, f, c] for (v, f), c in samples.items()]]
                              for key, samples in result.terrain.samples.items()])
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(value), encoding="utf-8")
        return result

    def get(self, kind, subid=0, *, terrain=None):
        try:
            variants = self.templates[kind, subid]
        except KeyError:
            raise ValueError(f"required game template missing: {kind}/{subid}") from None
        variants = sorted(variants, key=lambda t: (
            t.animation_file.lower() != b"avcranf0.def", -t.terrain_mask.bit_count(),
        ))
        for template in variants:
            if terrain is None or template.allows_terrain(terrain):
                return template
        raise ValueError(f"no template {kind}/{subid} for terrain {terrain}")


def _walk(terrain, start, blocked=frozenset()):
    """Conservative cardinal access; guarantees paths without corner cutting."""
    if start in blocked or terrain.tile(*start).terrain in (Terrain.WATER, Terrain.ROCK):
        return set()
    seen, queue = {start}, deque([start])
    while queue:
        x, y, z = queue.popleft()
        for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            cell = (x + dx, y + dy, z)
            if (0 <= cell[0] < terrain.size and 0 <= cell[1] < terrain.size
                    and cell not in seen and cell not in blocked
                    and terrain.tile(*cell).terrain not in (Terrain.WATER, Terrain.ROCK)):
                seen.add(cell)
                queue.append(cell)
    return seen


def _route(terrain, start, end):
    previous, queue = {start: None}, deque([start])
    while queue:
        cell = queue.popleft()
        if cell == end:
            result = []
            while cell is not None:
                result.append(cell)
                cell = previous[cell]
            return result
        x, y, z = cell
        for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            other = (x + dx, y + dy, z)
            if (0 <= other[0] < terrain.size and 0 <= other[1] < terrain.size
                    and other not in previous
                    and terrain.tile(*other).terrain not in (Terrain.WATER, Terrain.ROCK)):
                previous[other] = cell
                queue.append(other)
    raise ValueError(f"no route from {start} to {end}")


def landscape(spec):
    """Coarse 2x2 cells prevent the unsupported single-tile slivers of old maps."""
    n = spec.size // 2
    count = len(spec.zones)
    radius = min(n * .22, n * .68 / count)
    centers = {}
    rng = Random(spec.seed)
    phases = [rng.random() * 2 * pi for _ in spec.zones]
    for i, zone in enumerate(spec.zones):
        angle = pi + 2 * pi * i / count
        centers[zone.id] = (round(n / 2 + n * .29 * cos(angle)),
                            round(n / 2 + n * .29 * sin(angle)))
    coarse = [[int(Terrain.WATER)] * n for _ in range(n)]
    for i, zone in enumerate(spec.zones):
        cx, cy = centers[zone.id]
        for y in range(2, n - 2):
            for x in range(2, n - 2):
                # Low amplitude lobes create broad bays without tiny holes.
                extent = radius + .6 * sin(x * .55 + phases[i]) * cos(y * .45 + phases[i])
                if hypot(x - cx, y - cy) <= extent + 1:
                    coarse[y][x] = int(Terrain.SAND)
                if hypot(x - cx, y - cy) <= extent - 1:
                    coarse[y][x] = int(Terrain[zone.terrain.upper()])
    for a, b in spec.connections:
        ax, ay = centers[a]
        bx, by = centers[b]
        steps = max(abs(ax - bx), abs(ay - by))
        for step in range(steps + 1):
            x = round(ax + (bx - ax) * step / steps)
            y = round(ay + (by - ay) * step / steps)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if coarse[y + dy][x + dx] == Terrain.WATER:
                        coarse[y + dy][x + dx] = int(Terrain.SAND)
    data = bytearray()
    for y in range(spec.size):
        for x in range(spec.size):
            data.extend((coarse[y // 2][x // 2], 0, 0, 0, 0, 0, 0))
    return TerrainMap(bytes(data), spec.size, 1), {
        key: (x * 2, y * 2, 0) for key, (x, y) in centers.items()
    }


@dataclass
class World:
    map: mapfile.H3Map
    centers: dict
    reserved: set
    report: dict


def scenery_for(assets, terrain):
    """Biome palettes exclude editor props, fire effects and arbitrary junk."""
    palettes = {
        Terrain.GRASS: {115, 120, 122, 130, 134, 135, 137, 140},
        Terrain.DIRT: {115, 130, 133, 134, 135, 137, 140},
        Terrain.SAND: {116, 134, 138, 140},
        Terrain.SNOW: {119, 133, 134, 137, 140},
        Terrain.SWAMP: {115, 131, 132, 135, 137, 140},
        Terrain.ROUGH: {116, 133, 134, 138, 140},
        Terrain.LAVA: {127, 128, 134, 140},
        Terrain.HIGHLANDS: {115, 133, 134, 135, 137, 140},
        Terrain.WASTELAND: {116, 119, 133, 134, 138, 140},
    }
    return [t for t in assets.decorations if t.object_id in palettes.get(terrain, ())
            and t.allows_terrain(terrain)
            and (t.object_id != 140 or t.animation_file.lower().startswith(b"avlr"))]


class Placement:
    def __init__(self, parsed, reserved):
        self.map = parsed
        self.reserved = reserved
        self.occupied = set()
        self.anchors = set()
        self.interactions = []

    def cells(self, template, position):
        x, y, z = position
        offsets = set(template.blocked_cells()) | set(template.visitable_cells()) | {(0, 0)}
        return {(x + dx, y + dy, z) for dx, dy in offsets}

    def fits(self, template, position):
        cells = self.cells(template, position)
        return not cells & (self.occupied | self.reserved) and all(
            0 <= x < self.map.header.size and 0 <= y < self.map.header.size
            and self.map.terrain.tile(x, y, z).terrain not in (Terrain.WATER, Terrain.ROCK)
            and template.allows_terrain(self.map.terrain.tile(x, y, z).terrain)
            for x, y, z in cells
        )

    def place(self, template, position, payload=b"", *, interactive=False):
        if not self.fits(template, position):
            raise ValueError(f"object does not fit: {template} at {position}")
        approaches = set()
        if interactive:
            x, y, z = position
            visits = template.visitable_cells()
            if not visits:
                raise ValueError("interactive object has no visit tile")
            footprint = self.cells(template, position)
            # Reserve the southern approach to every actual visit tile.
            # Native towns and mines allow interaction from this direction.
            for dx, dy in visits:
                cell = (x + dx, y + dy + 1, z)
                if cell not in footprint and 0 <= cell[1] < self.map.header.size:
                    if (cell not in self.occupied
                            and self.map.terrain.tile(*cell).terrain not in (Terrain.WATER, Terrain.ROCK)):
                        approaches.add(cell)
            if not approaches:
                raise ValueError("object has no free southern approach")
            # Connect to the existing path before decorating.
            local_paths = [p for p in self.reserved if p[2] == z]
            if not local_paths:
                raise ValueError("no reserved path on this map level")
            start = min(local_paths, key=lambda p: abs(p[0]-position[0])+abs(p[1]-position[1]))
            access = sorted(approaches)[0]
            path = _route(self.map.terrain, start, access)
            if set(path) & (self.occupied | footprint):
                raise ValueError("object approach crosses an occupied footprint")
            self.reserved.update(path)
            self.reserved.update(approaches)
            self.interactions.append(access)
        catalog.place(self.map, catalog.BorrowedObject(template, b"", "local catalog"),
                      *position, payload=payload)
        self.occupied.update(self.cells(template, position))
        self.anchors.add(position)

    def near(self, template, center, payload, *, radius=12):
        x, y, z = center
        positions = [(x + dx, y + dy, z) for dy in range(-radius, radius + 1)
                     for dx in range(-radius, radius + 1)]
        positions.sort(key=lambda p: (abs(p[0]-x) + abs(p[1]-y), p[1], p[0]))
        for position in positions:
            if self.fits(template, position):
                try:
                    self.place(template, position, payload, interactive=True)
                    return position
                except ValueError:
                    continue
        raise ValueError(f"no accessible placement near {center}: {template}")


def generate_world(spec: WorldSpec, assets: Assets) -> World:
    spec.validate()
    terrain, centers = landscape(spec)
    assets.terrain.apply(terrain, spec.seed)
    parsed = hota.new_map(spec.name, "Создано h3m-forge. Зоны и связи из JSON.",
                          size=spec.size, players=sum(z.player is not None for z in spec.zones))
    parsed.terrain = terrain
    reserved = set()
    for a, b in spec.connections:
        reserved.update(_route(terrain, centers[a], centers[b]))
    placement = Placement(parsed, reserved)
    towns = {}
    for number, zone in enumerate(spec.zones):
        center = centers[zone.id]
        if zone.player is not None:
            # Default random town, all HotA factions allowed by player settings.
            template = assets.get(Obj.RANDOM_TOWN)
            position = placement.near(template, (center[0]+2, center[1]-2, 0),
                                      hota.town_payload(number + 1, zone.player))
            player = parsed.players[zone.player]
            player.has_main_town = 1
            player.generate_hero_at_main_town = 1
            player.main_town_type = 255
            player.main_town_pos = (position[0]-2, position[1], 0)
            towns[zone.id] = position
            # Sawmill and ore pit: owner is an explicit neutral uint32.
            for mine in (0, 2):
                placement.near(assets.get(Obj.MINE, mine, terrain=Terrain[zone.terrain.upper()]),
                               center, struct.pack("<I", 255))
        for resource in (0, 2, 6):
            # Resource amount is in native units (gold units are 100 gold).
            placement.near(assets.get(Obj.RESOURCE, resource), center,
                           b"\0" + struct.pack("<I", 10) + bytes(4))
        # Two random/default sentinels, observed on 1376 native HotA chests.
        placement.near(assets.get(Obj.TREASURE_CHEST), center, b"\xff" * 8)
    rng = Random(spec.seed)
    palettes = {terrain: scenery_for(assets, terrain) for terrain in Terrain}
    positions = [(x, y, 0) for y in range(3, spec.size - 2) for x in range(5, spec.size - 2)]
    rng.shuffle(positions)
    decorations = 0
    for position in positions:
        terrain_type = terrain.tile(*position).terrain
        density = spec.decoration_density * (0.35 if terrain_type == Terrain.SAND else 1)
        if rng.random() >= density:
            continue
        candidates = list(palettes[terrain_type])
        rng.shuffle(candidates)
        for template in candidates[:12]:
            if placement.fits(template, position):
                placement.place(template, position)
                decorations += 1
                break
    seen = _walk(terrain, next(iter(centers.values())), placement.occupied)
    required = set(centers.values()) | set(placement.interactions) | reserved
    if required - seen:
        raise ValueError(f"unreachable required cells: {sorted(required - seen)[:5]}")
    raw = mapfile.serialize(parsed)
    check = mapfile.parse(raw)
    if check.stopped_at or check.tail or check.events is None or mapfile.serialize(check) != raw:
        raise ValueError(f"generated map failed complete parse: {check.stopped_at}")
    report = dict(format="HotA 1.8.0 / revision 9", seed=spec.seed, size=spec.size,
                  zones=len(spec.zones), objects=len(parsed.objects), decorations=decorations,
                  terrain_reference_maps=assets.terrain.sources, towns=towns,
                  reachable_required_cells=len(required), full_parse=True, roundtrip=True,
                  limitations=["surface only", "land bridges; no sailing",
                               "no combat balance or scripted quests", "connections are not exclusive"])
    return World(parsed, centers, reserved, report)
