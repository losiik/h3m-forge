"""Themed coastal obstacles with native templates and fully blocked land caps."""
from collections import Counter
from random import Random

from h3m import catalog
from h3m.terrain import Terrain


THEMES = {
    'troy': ('Каменистая ахейская стоянка', Terrain.DIRT, (136, 140, 135)),
    'ismar': ('Лесистые мысы киконов', Terrain.GRASS, (135, 137, 140)),
    'lotus': ('Дюны и пальмы лотофагов', Terrain.SAND, (134, 140, 130)),
    'cyclops': ('Кручи Полифема', Terrain.ROUGH, (134, 136, 140)),
    'aeolus': ('Горные уступы Эолии', Terrain.HIGHLANDS, (134, 140)),
    'giants': ('Каменные стены лестригонов', Terrain.WASTELAND, (134, 136, 140)),
    'circe': ('Лесные мысы Кирки', Terrain.GRASS, (135, 137, 140)),
    'sirens': ('Песчаные косы и столбы сирен', Terrain.SAND, (134, 140, 130)),
    'scylla': ('Утёсы Сциллы', Terrain.ROUGH, (134, 136, 140)),
    'helios': ('Зелёные мысы Тринакрии', Terrain.GRASS, (135, 136, 140)),
    'calypso': ('Заросшие берега Огигии', Terrain.GRASS, (135, 137, 140)),
    'phaeacia': ('Рощи феаков', Terrain.GRASS, (135, 137, 140)),
    'ithaca': ('Каменистая Итака', Terrain.GRASS, (136, 135, 140)),
    'lights': ('Отмели у огней родины', Terrain.SAND, (134, 140, 130)),
}


def _footprint(template, anchor):
    x, y, z = anchor
    return {(x+dx, y+dy, z) for dx, dy in template.blocked_cells()}


def natural_cap_template(t, terrain):
    # HotA reuses scenery IDs for walls and custom graphics. Curate native
    # families as well as IDs; otherwise a "rock" can become a stone staircase.
    name=t.animation_file.lower()
    if terrain == Terrain.SAND:
        return name.startswith((b'avlmtdn', b'avlspl', b'avldlog'))
    prefixes={134:(b'avlm',), 135:(b'avlaut', b'avlsptr', b'avloak'),
              136:(b'avloc', b'avlo'), 137:(b'avlpntr',), 140:(b'avlr',)}
    return name.startswith(prefixes.get(t.object_id, ()))


def place_barriers(m, assets, islands, reefs, lanes, occupied, seed):
    """Replace sections of the reef wall with impassable, decorated headlands.

    Every new land cell is covered by a real blocking mask. This prevents
    landing on a new cape and walking around a chapter gate. No template
    masks or terrain permissions are fabricated.
    """
    rng = Random(seed)
    regions = []
    land_obstacles = set()
    data = bytearray(m.terrain.data)
    for island in islands:
        if island.z:
            continue
        title, terrain, preferred = THEMES[island.key]
        x, y = island.x, island.y
        # Even 2x2 blocks retain the terrain catalog's supported coast shapes.
        # Vary the lengths and which side gets the largest cape per episode.
        long_side = sum(island.key.encode()) % 3
        lengths = [8 if side == long_side else 4 for side in range(3)]
        patches = [
            {(x+dx, y+dy, 0) for dx in range(-lengths[0]//2, lengths[0]//2) for dy in (-8, -7)},
            {(x+dx, y+dy, 0) for dx in (-8, -7) for dy in range(-lengths[1]//2, lengths[1]//2)},
            {(x+dx, y+dy, 0) for dx in (6, 7) for dy in range(-lengths[2]//2, lengths[2]//2)},
        ]
        cells = set.union(*patches)
        if cells & (occupied | lanes) or any(not m.terrain.tile(*c).is_water for c in cells):
            raise ValueError(f'Coastal obstacle conflicts with island: {island.key}')
        for c in cells:
            data[m.terrain.offset_of(*c)] = terrain
        land_obstacles.update(cells)
        regions.append(dict(island=island.key, title=title, terrain=int(terrain),
                            cells=sorted(cells), preferred=preferred))
    m.terrain.data = bytes(data)
    assets.terrain.apply(m.terrain, seed=seed)

    land_counts = Counter()
    for region in regions:
        remaining = set(map(tuple, region['cells']))
        preferred = region.pop('preferred')
        palette = [t for ts in assets.templates.values() for t in ts if t.object_id in preferred
                   and t.allows_terrain(region['terrain']) and not t.visitable_cells()
                   and t.blocked_cells() and natural_cap_template(t,region['terrain'])]
        # Large native footprints first; use small rocks only for remaining gaps.
        rng.shuffle(palette)
        palette.sort(key=lambda t: (preferred.index(t.object_id), -len(t.blocked_cells())))
        for t in palette:
            # The sprite anchor may itself be passable/already occupied; use
            # the actual blocked mask when fitting, not the remaining anchors.
            anchors = sorted(map(tuple, region['cells']), reverse=True)
            for anchor in anchors:
                footprint = _footprint(t, anchor)
                if not footprint or not footprint <= remaining:
                    continue
                catalog.place(m, catalog.BorrowedObject(t, b'', 'themed cape'), *anchor)
                remaining.difference_update(footprint)
                land_counts[t.object_id] += 1
        if remaining:
            raise ValueError(f'Unblocked landing on cape {region["island"]}: {sorted(remaining)}')
    occupied.update(land_obstacles)

    # Native sea rocks include multi-cell shapes; ruins punctuate two episodes.
    water_templates = {t.animation_file: t for ts in assets.templates.values() for t in ts
                       if t.object_id in (147, 161) and t.allows_terrain(Terrain.WATER)
                       and t.blocked_cells() and not t.visitable_cells()}
    pillars = sorted({t.animation_file: t for ts in assets.templates.values() for t in ts
                      if t.object_id == 139 and t.animation_file.lower().startswith(b'avlpilr')
                      and t.allows_terrain(Terrain.WATER) and t.blocked_cells() == [(0, 0)]
                      and not t.visitable_cells()}.values(), key=lambda t: t.animation_file)
    remaining = set(reefs) - land_obstacles
    water_counts = Counter()
    multicell = 0
    for key in ('sirens', 'giants'):
        i = next(i for i in islands if i.key == key)
        spots = sorted(c for c in remaining if abs(c[0]-i.x) <= 7 and abs(c[1]-i.y) <= 7)
        for c in spots[::max(1, len(spots)//6)][:6]:
            if not pillars:
                break
            t = rng.choice(pillars)
            catalog.place(m, catalog.BorrowedObject(t, b'', 'sea pillars'), *c)
            remaining.remove(c)
            occupied.add(c)
            water_counts[t.object_id] += 1
    palette = sorted(water_templates.values(), key=lambda t: (-len(t.blocked_cells()), t.animation_file))
    # Exact packing preserves the old fairways; no extra blocked water cells.
    for t in palette:
        if len(t.blocked_cells()) == 1:
            continue
        for c in sorted(remaining, reverse=True):
            footprint = _footprint(t, c)
            if footprint <= remaining:
                catalog.place(m, catalog.BorrowedObject(t, b'', 'sea rock group'), *c)
                remaining.difference_update(footprint)
                occupied.update(footprint)
                water_counts[t.object_id] += 1
                multicell += 1
    singles = [t for t in palette if t.blocked_cells() == [(0, 0)]]
    for c in sorted(remaining):
        if c in occupied:
            raise ValueError(f'Coastal barrier overlaps object: {c}')
        t = rng.choice(singles)
        catalog.place(m, catalog.BorrowedObject(t, b'', 'sea rock'), *c)
        occupied.add(c)
        water_counts[t.object_id] += 1
    return dict(regions=regions, land_cells=len(land_obstacles),
                land_objects=dict(land_counts), water_objects=dict(water_counts),
                multi_cell_water_objects=multicell,
                blocked_land_cells=sorted(land_obstacles))
