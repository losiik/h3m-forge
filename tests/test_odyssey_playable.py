"""Regressions for the user's twenty-minute playthrough feedback."""
from copy import deepcopy

import pytest

from h3m import mapfile, paths
from h3m.adventure import read_monster, read_reward
from h3m.world import Assets
from odyssey.playable import generate, validate, parse_quest


@pytest.fixture(scope='module')
def adventure():
    try:
        files = [p for p in paths.iter_maps() if not p.name.startswith('Odyssey-Homecoming')]
    except paths.GameNotFoundError:
        pytest.skip('installed HotA assets required')
    return generate(Assets.cached(files,paths.out_dir()/'world-assets.json'))


def test_actions_open_chapters_and_no_combat_trophy_delivery(adventure):
    m,r = adventure
    assert r['kill_objective_gates'] == 7 and r['total_battles'] == 23
    assert r['estimated_hours'] is None and not r['full_playtest']
    assert len(r['scenes']) == 13 and len(r['quests']) == 9
    assert all(read_monster(o.payload)['artifact']==65535 for o in m.objects if o.object_id==54)
    quests = [parse_quest(o.payload,hut=True) for o in m.objects if o.object_id==83]
    assert next(q for q in quests if q['reward']==36)['required'] == (30045,)
    trace = r['progression_trace']
    assert trace.index('battle:50000') < trace.index('gate:ismar')
    assert trace.index('battle:40002') < trace.index('gate:scylla')
    assert trace.index('battle:50002') < trace.index('gate:ithaca')
    assert mapfile.serialize(mapfile.parse(mapfile.serialize(m))) == mapfile.serialize(m)


def test_optional_rewards_are_not_required_for_completion(adventure):
    original,r = adventure
    m = deepcopy(original)
    optional = {tuple(c['position']) for c in r['choices'] if c['optional']}
    assert len(optional)==6
    m.objects = [o for o in m.objects if not (o.object_id==6 and o.position in optional)]
    assert validate(m,r)['guaranteed_quest_supplies']


def test_one_reef_hole_is_detected(adventure):
    original,r = adventure
    m = deepcopy(original)
    reef = min((o for o in m.objects if o.object_id in (147,161) and o.y==76 and o.x<18),key=lambda o:o.x)
    m.objects.remove(reef)
    with pytest.raises(ValueError,match='physical bypass into ismar'):
        validate(m,r)


def test_nonexistent_monster_target_is_rejected(adventure):
    original,r = adventure
    m,r = deepcopy(original),deepcopy(r)
    gate = next(g for g in r['harbour_guards'] if g['island']=='ismar')
    obj = next(o for o in m.objects if o.object_id==215 and list(o.position)==gate['position'])
    obj.payload = obj.payload[:1] + (999999).to_bytes(4,'little') + obj.payload[5:]
    gate['required'] = (999999,)
    with pytest.raises(ValueError,match='missing monster'):
        validate(m,r)


def test_disabled_human_arrival_event_is_rejected(adventure):
    original,r = adventure
    m = deepcopy(original)
    event = next(o for o in m.objects if o.object_id==26)
    event.payload = event.payload[:-14]+b'\0'+event.payload[-13:]
    with pytest.raises(ValueError,match='will not activate'):
        validate(m,r)


def test_missing_moly_supply_deadlocks_the_actual_quest(adventure):
    original,r = adventure
    m = deepcopy(original)
    m.objects = [o for o in m.objects if not (o.object_id==6 and read_reward(o.payload)['resources'][5])]
    with pytest.raises(ValueError,match='Progression deadlock'):
        validate(m,r)
