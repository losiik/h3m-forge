from copy import deepcopy
import struct

import pytest

from h3m import mapfile, paths
from h3m.adventure import read_reward
from h3m.pacing import audit_landings, audit_sea_legs
from h3m.world import Assets
from odyssey.compact import generate
from odyssey.playable import validate


@pytest.fixture(scope='module')
def compact():
    try:
        files=[p for p in paths.iter_maps() if not p.name.startswith('Odyssey-Homecoming')]
    except paths.GameNotFoundError:
        pytest.skip('installed HotA assets required')
    return generate(Assets.cached(files,paths.out_dir()/'world-assets.json'))


def test_compact_travel_budget_and_full_progression(compact):
    m,r=compact
    assert m.header.size==72 and r['gameplay_revision']==4
    assert r['pacing']['max_steps']<=30
    assert r['pacing']['total_steps']<r['pacing_previous']['total_steps']*.5
    assert r['shore_access']['max_steps']<=12
    assert len(r['bargains'])==3
    assert r['no_early_island_access'] and r['sequential_playthrough_model']
    assert r['progression_trace'][-1]=='quest:36'
    assert mapfile.serialize(mapfile.parse(mapfile.serialize(m)))==mapfile.serialize(m)
    town=next(o for o in m.objects if o.object_id==98 and o.payload[4]==0)
    assert m.players[0].main_town_pos==(town.x-2,town.y,town.z)
    assert tuple(m.loss.payload)==tuple(r['start'])
    assert r['landings']['checked']==14


def test_missing_cyclops_coastal_bit_reproduces_landing_failure(compact):
    m,r=compact
    broken=deepcopy(m)
    beach=next(x['beach'] for x in r['landings']['harbours'] if x['island']=='cyclops')
    raw=bytearray(broken.terrain.data)
    raw[broken.terrain.offset_of(*beach)+6]&=~0x40
    broken.terrain.data=bytes(raw)
    with pytest.raises(ValueError,match='Native landing disabled at cyclops'):
        audit_landings(broken,{'cyclops':tuple(beach)})


def test_required_action_distance_budget_is_enforced(compact):
    m,r=compact
    leg=max(r['pacing']['legs'],key=lambda x:x['steps'])
    with pytest.raises(ValueError,match='exceeds budget'):
        audit_sea_legs(m,[(leg['label'],leg['start'],leg['end'])],max_steps=leg['steps']-1)


def test_can_finish_without_paid_bargains_or_optional_rewards(compact):
    original,r=compact
    m=deepcopy(original)
    optional={(6,tuple(c['position'])) for c in r['choices'] if c['optional']}
    optional|={(83,tuple(c['position'])) for c in r['bargains']}
    m.objects=[o for o in m.objects if (o.object_id,o.position) not in optional]
    assert validate(m,r)['guaranteed_quest_supplies']


def test_bargain_route_really_replaces_guarded_supply(compact):
    from h3m.adventure import Reward
    original,r=compact
    m=deepcopy(original)
    # Supply gold before Cyclops and remove all three guarded resource boxes.
    for o in m.objects:
        if o.object_id==6 and read_reward(o.payload)['message'].startswith('Припасы для выхода'):
            o.payload=Reward('Тестовый бюджет мастеров',resources=(0,0,0,0,0,0,23000)).pandora()
    supply={(6,tuple(c['position'])) for c in r['choices'] if c['guards'] and not c['optional']}
    m.objects=[o for o in m.objects if (o.object_id,o.position) not in supply]
    assert validate(m,r)['sequential_playthrough_model']


def test_compact_reef_removal_is_a_real_bypass(compact):
    original,r=compact
    m=deepcopy(original)
    m.objects=[o for o in m.objects if o.object_id not in (147,161)]
    with pytest.raises(ValueError,match='physical bypass'):
        validate(m,r)


def test_optional_spells_have_tactical_effect_not_travel_shortcuts(compact):
    m,r=compact
    spells=[s for o in m.objects if o.object_id==6 for s in read_reward(o.payload)['spells']]
    assert sorted(spells)==[37,44]
    # Native hero slot 0 contains the Admiral's Hat; slot 17 the spellbook.
    from h3m.stream import BinaryReader
    hero=next(o for o in m.objects if o.object_id==34)
    b=BinaryReader(hero.payload)
    b.bytes_(7); b.string(); b.bytes_(6); assert b.u8()==1
    b.bytes_(b.u32()*2); assert b.u8()==1
    b.bytes_(28); b.u8(); assert b.u8()==1
    slots=[(b.u16(),b.u16()) for _ in range(19)]
    assert slots[0]==(136,0) and slots[17]==(0,0)
