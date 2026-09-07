"""Native field regressions and end-to-end quest supply / travel checks."""
import struct
from copy import deepcopy

import pytest

from h3m import hota, mapfile, paths
from h3m.terrain import Terrain
from h3m.world import Assets, Placement
from odyssey import payloads as p
from odyssey.story import generate
from odyssey.navigation import validate_progression


@pytest.fixture(scope='module')
def assets():
    try:
        files = [f for f in paths.iter_maps() if not f.name.startswith('Odyssey-Homecoming')]
    except paths.GameNotFoundError:
        pytest.skip('installed HotA assets required')
    return Assets.cached(files, paths.out_dir()/'world-assets.json')


@pytest.fixture(scope='module')
def adventure(assets):
    return generate(assets)


def test_regular_artifacts_match_native_editor_convention():
    # Match the ordinary artifact representation in editor-authored HotA maps.
    assert p.artifact(7) == bytes.fromhex('07000000')
    assert p.artifact(65535) == bytes.fromhex('ffffffff')
    seer = p.seer((7,40),8,'Начало','Конец')
    assert seer[:14] == bytes.fromhex('0100000005020700000028000000')
    assert seer[-11:] == bytes.fromhex('0808000000000000000000')


def test_scylla_cost_removes_six_pikemen():
    data = p.seer(((0,6),),43,'Шесть спутников','Прощайте',mission=6)
    assert data[:10] == bytes.fromhex('01000000060100000600')


def test_hota_box_difficulty_and_movement_fields():
    data = p.box('Дар', army=((3,20),))
    assert data[-14:] == b'\x00'+struct.pack('<iiiB',0,0,31,0)


def test_routes_stay_on_correct_level(assets):
    m = hota.new_map('Two levels',size=36,two_levels=True,terrain=Terrain.GRASS)
    placement = Placement(m,{(12,15,1),(12,15,0)})
    placement.place(assets.get(83), (15,14,0), p.seer((7,),8,'A','B'),interactive=True)
    assert m.objects[-1].z == 0


def test_full_story_is_serialized_and_connected(assets,adventure):
    m, report = adventure
    assert report['quest_chain_valid'] and report['all_story_objects_accessible']
    assert report['all_harbours_connected_after_unlocking']
    assert len(report['chapters']) == 16 and len(report['islands']) == 15
    assert report['decorations'] > 400
    parsed = mapfile.parse(mapfile.serialize(m))
    assert parsed.stopped_at is None and not parsed.tail
    assert len(parsed.playable_players) == 1
    # Native artifact victory fixes this flag to 1. The single-player map
    # suppresses elimination victory, so obtaining the final sign is required.
    assert parsed.victory.allow_normal_victory == 1
    assert parsed.victory.payload == struct.pack('<H',36)
    heroes = [o for o in parsed.objects if o.object_id == 34]
    assert len(heroes) == 1
    assert parsed.loss.payload == bytes([heroes[0].x-1,heroes[0].y,heroes[0].z])
    assert len([o for o in parsed.objects if o.object_id == 8]) == 1
    assert {(o.x,o.y,o.z) for o in parsed.objects if o.object_id == 103} == {(128,68,0),(128,68,1)}
    assert mapfile.serialize(parsed) == mapfile.serialize(m)
    assert mapfile.serialize(generate(assets)[0]) == mapfile.serialize(m)


def audit(m,r):
    return validate_progression(m,r['chapters'],r['challenges'],r['harbour_guards'],r['sea_encounters'])


def test_reefs_enforce_order_and_mandatory_sea_battles(adventure):
    m,r=adventure
    assert r['no_early_island_access'] and r['no_early_sea_trials']
    assert r['sequential_playthrough_model'] and r['sea_battles']==7 and r['total_battles']==11
    assert {e['creature'] for e in r['sea_encounters']}=={115,153,154}
    assert len(r['harbour_guards'])==14
    trace=r['progression_trace']
    assert trace.index('chapter:03. Никто') < trace.index('battle:aeolus')
    assert trace.index('chapter:15. Рассказ у Алкиноя') < trace.index('gate:ithaca')
    assert trace.index('chapter:08. Чары Кирки') < trace.index('gate:hades')
    # The entry guard consumes the key; its seer must never require it again.
    for c in r['chapters']:
        if c['entry_required'] is not None and c['mission']==5:
            assert c['entry_required'] not in c['required']


def test_missing_reef_ring_is_detected_as_actual_shortcut(adventure):
    original,r=adventure
    m=deepcopy(original)
    m.objects=[o for o in m.objects if o.object_id not in (147,161)]
    with pytest.raises(ValueError,match='physical bypass'):
        audit(m,r)


def test_one_missing_reef_also_opens_a_detectable_shortcut(adventure):
    original,r=adventure
    m=deepcopy(original)
    # Western edge of Ismar's ring: one-cell hole, not removal of the whole barrier.
    candidates=[o for o in m.objects if o.object_id in (147,161) and o.y==76 and o.x<18]
    reef=min(candidates,key=lambda o:o.x)
    m.objects.remove(reef)
    with pytest.raises(ValueError,match='physical bypass into ismar'):
        audit(m,r)


def test_native_guard_key_mutation_is_detected(adventure):
    original,r=adventure
    m=deepcopy(original)
    gate=next(o for o in m.objects if o.object_id==215)
    gate.payload=gate.payload[:2]+p.artifact(99)+gate.payload[6:]
    with pytest.raises(ValueError,match='serialized guard condition differs'):
        audit(m,r)


def test_closed_route_without_required_entry_key_deadlocks(adventure):
    original,r=adventure
    m=deepcopy(original)
    r=deepcopy(r)
    g=next(g for g in r['harbour_guards'] if g['island']=='aeolus')
    o=next(o for o in m.objects if o.object_id==215 and [o.x,o.y,o.z]==g['position'])
    g['required']=[99]
    o.payload=o.payload[:2]+p.artifact(99)+o.payload[6:]
    with pytest.raises(ValueError,match='progression deadlock'):
        audit(m,r)
