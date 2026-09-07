"""Semantic generation checks, in addition to binary round trips."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from h3m import hota, mapfile, paths
from h3m.autotile import TerrainCatalog
from h3m.format import MapFormat
from h3m.terrain import Terrain, TerrainMap
from h3m.world import Assets, WorldSpec, Zone, _walk, generate_world


ROOT = Path(__file__).resolve().parents[1]


def example():
    return WorldSpec.from_dict(json.loads((ROOT / "examples/archipelago.json").read_text("utf-8")))


def test_native_hota_profile():
    original = hota.new_map("Тест HotA", size=72, players=2)
    raw = mapfile.serialize(original)
    parsed = mapfile.parse(raw)
    assert parsed.header.format is MapFormat.HOTA
    assert parsed.header.hota.level == 9
    assert parsed.header.hota.version_string == "1.8.0"
    assert parsed.stopped_at is None and not parsed.tail
    assert parsed.events is not None
    assert parsed.meta.options.round_limit == -1
    assert parsed.meta.allowed_heroes.declared_count == 215
    assert parsed.meta.allowed_artifacts.declared_count == 166
    assert all(p.allowed_factions == 4095 for p in parsed.playable_players)
    assert mapfile.serialize(parsed) == raw


def test_profile_matches_editor_probe_when_available():
    probe = ROOT / "out/probe_town.h3m"
    if not probe.exists():
        pytest.skip("local editor reference unavailable")
    parsed = mapfile.load(probe)
    generated = hota.new_map("Profile")
    assert generated.header.hota == parsed.header.hota
    assert generated.meta == parsed.meta
    assert generated.predefined_heroes == parsed.predefined_heroes
    reference = parsed.objects[0].payload
    assert hota.town_payload(int.from_bytes(reference[:4], "little"), 255) == reference


@pytest.mark.parametrize("change", [
    {"size": 36}, {"seed": "one"}, {"name": ""}, {"decoration_density": .9},
    {"connections": ()}, {"connections": (("west", "missing"),)},
    {"connections": (("west", "west"),)},
    {"zones": (Zone("a", player=0), Zone("a", player=1))},
    {"zones": (Zone("a", player=0), Zone("b", player=0))},
    {"zones": (Zone("a", player=0), Zone("b", "water", player=1))},
])
def test_invalid_specs_fail_before_reading_game(change):
    with pytest.raises((ValueError, TypeError)):
        replace(example(), **change).validate()


def test_missing_terrain_reference_is_atomic_error():
    terrain = TerrainMap(bytes([Terrain.GRASS, 49, 0, 0, 0, 0, 0]) * 25, 5, 1)
    before = terrain.data
    with pytest.raises(ValueError, match="No terrain reference"):
        TerrainCatalog().apply(terrain)
    assert terrain.data == before


def test_terrain_mirroring_preserves_road_and_river_flags():
    source = TerrainMap(bytes([Terrain.GRASS, 49, 0, 0, 0, 0, 3]) * 25, 5, 1)
    catalog = TerrainCatalog()
    catalog.learn(source)
    target = TerrainMap(bytes([Terrain.GRASS, 0, 1, 2, 1, 3, 0x3c]) * 25, 5, 1)
    catalog.apply(target)
    tile = target.tile(2, 2)
    assert tile.flags == 0x3f
    assert (tile.road, tile.road_dir, tile.river, tile.river_dir) == (1, 3, 1, 2)


def test_blocked_start_does_not_leak_reachability():
    terrain = TerrainMap(bytes([Terrain.GRASS, 49, 0, 0, 0, 0, 0]) * 25, 5, 1)
    assert _walk(terrain, (2, 2, 0), {(2, 2, 0)}) == set()


def test_coastal_flags_follow_water_not_ambiguous_sand_samples():
    # Sand's rendering key ignores all neighbours, so a valid learned inland
    # frame is reused at the sea. Its missing coast bit must not be copied.
    source=TerrainMap(bytes([Terrain.SAND,0,0,0,0,0,0])*25,5,1)
    water=TerrainMap(bytes([Terrain.WATER,0,0,0,0,0,0])*25,5,1)
    catalog=TerrainCatalog(); catalog.learn(source); catalog.learn(water)
    target=TerrainMap(source.data,5,1)
    for y in range(5):
        for x in (3,4): target.set_tile(x,y,0,Terrain.WATER,0)
    # Supply rendering references for the mixed coastline as well.
    catalog.learn(target)
    catalog.apply(target)
    assert target.tile(2,2).flags & 0x40
    assert not target.tile(1,2).flags & 0x40
    # Conversely an inland cell must not retain a coastal sample's flag.
    for samples in catalog.samples.values():
        for key,count in list(samples.items()):
            del samples[key]; samples[(key[0],key[1]|0x40)]=count
    inland=TerrainMap(source.data,5,1)
    catalog.apply(inland)
    assert not inland.tile(2,2).flags & 0x40


@pytest.fixture(scope="module")
def assets():
    try:
        files = list(paths.iter_maps())
    except paths.GameNotFoundError:
        pytest.skip("installed game required for integration test")
    if not files:
        pytest.skip("installed map corpus is empty")
    return Assets.cached(files, paths.out_dir() / "world-assets.json")


@pytest.mark.parametrize("seed", [0, 1, 42, 999])
def test_generated_world_access_and_footprints(assets, seed):
    spec = replace(example(), seed=seed, decoration_density=.4)
    world = generate_world(spec, assets)
    m = world.map
    taken = set()
    visits = []
    for obj in m.objects:
        t = m.object_templates[obj.template_index]
        cells = {(obj.x+dx, obj.y+dy, obj.z) for dx, dy in
                 set(t.blocked_cells()) | set(t.visitable_cells()) | {(0, 0)}}
        assert not cells & taken
        assert not cells & world.reserved
        for cell in cells:
            assert m.terrain.tile(*cell).terrain not in (Terrain.WATER, Terrain.ROCK)
        taken |= cells
        visits.extend((obj.x+dx, obj.y+dy+1, obj.z) for dx, dy in t.visitable_cells())
    seen = _walk(m.terrain, world.centers["west"], taken)
    assert set(world.centers.values()) <= seen
    assert set(visits) <= seen
    assert world.report["decorations"] > 30
    assert world.report["full_parse"] and world.report["roundtrip"]


def test_seed_is_reproducible(assets):
    spec = example()
    first = mapfile.serialize(generate_world(spec, assets).map)
    assert mapfile.serialize(generate_world(spec, assets).map) == first
    assert mapfile.serialize(generate_world(replace(spec, seed=43), assets).map) != first
