from copy import deepcopy

import pytest

from h3m import mapfile, paths
from h3m.adventure import Reward, read_reward, read_monster
from h3m.world import Assets
from odyssey.rewards_journey import generate
from odyssey.playable import validate, parse_quest


@pytest.fixture(scope='module')
def journey():
    try:files=[p for p in paths.iter_maps() if not p.name.startswith(('Odyssey-','Forge-'))]
    except paths.GameNotFoundError:pytest.skip('Native HotA references required')
    return generate(Assets.cached(files,paths.out_dir()/'world-assets.json'))


def test_finale_is_blue_hero_not_a_followup_artifact(journey):
    m,r=journey
    assert m.victory.kind==5 and not m.victory.allow_normal_victory
    assert m.victory.payload==bytes(r['finale']['visit'])
    assert 'battle:71000' in r['progression_trace']
    assert m.players[1].can_computer_play and not m.players[1].can_human_play
    wrong=deepcopy(m);wrong.victory.payload=bytes(r['finale']['position'])
    with pytest.raises(ValueError,match='Victory'):validate(wrong,r)
    misplaced=deepcopy(m)
    enemy=next(o for o in misplaced.objects if o.object_id==34 and o.payload[4]==1)
    enemy.y-=1
    with pytest.raises(ValueError,match='town footprint'):validate(misplaced,r)


def test_each_sea_fork_is_sufficient_but_one_fight_is_required(journey):
    m,r=journey
    for uid in (70101,70102):
        trace=validate(m,r,avoid_battles={uid})['progression_trace']
        assert f'battle:{uid}' not in trace and 'battle:71000' in trace
    with pytest.raises(ValueError,match='Progression deadlock'):
        validate(m,r,avoid_battles={70101,70102})


def test_monster_rewards_are_real_and_cyclops_eye_is_unique(journey):
    m,r=journey
    infos=[read_monster(o.payload) for o in m.objects if o.object_id==54]
    assert all(i.get('artifact',65535)!=65535 or any(i.get('resources',())) for i in infos)
    assert next(i for i in infos if i['identifier']==70010)['artifact']==101
    assert sum(i.get('artifact')==101 for i in infos)==1
    assert not any(i.get('artifact')==10 for i in infos)
    assert next(i for i in infos if i['identifier']==30042)['count']==16
    assert next(i for i in infos if i['identifier']==40002)['count']==160


def test_no_immediate_tolls_and_optional_preparation_can_be_skipped(journey):
    m,r=journey
    gates=[parse_quest(o.payload) for o in m.objects if o.object_id==215]
    assert all(q['mission'] in (4,8) for q in gates)
    assert r['mandatory_without_optional']
    huts=[parse_quest(o.payload,hut=True) for o in m.objects if o.object_id==83]
    assert all(q['mission']!=6 for q in huts)
    assert all(q['required'][-1]<7000 for q in huts if q['mission']==7)
    assert sum(q['required']==(101,) for q in huts)==2
    assert next(q for q in huts if q['reward']==99)['required']==(79,)


def test_ambushes_are_hidden_once_only_events(journey):
    m,r=journey
    assert len(r['ambushes'])==3
    for a in r['ambushes']:
        o=next(o for o in m.objects if o.object_id==26 and list(o.position)==a['position'])
        reward=read_reward(o.payload,event=True)
        assert reward['guards'] and reward['once'] and reward['human'] and reward['players']==1
        assert not reward['computer'] and not reward['uses_scripts']
    assert r['landings']['checked']==16 and r['shore_access']['max_steps']<=12
    assert len(r['training'])==12
    for ambush in r['ambushes']:
        with pytest.raises(ValueError,match='Progression deadlock'):
            validate(m,r,avoid_ambushes={tuple(ambush['position'])})


def test_extended_rewards_and_new_town_roundtrip(journey):
    m,r=journey
    assert mapfile.serialize(mapfile.parse(mapfile.serialize(m)))==mapfile.serialize(m)
    reward=read_reward(Reward('Training',primary=(1,2,3,4),skills=((15,2),)).pandora())
    assert reward['primary']==[1,2,3,4] and reward['skills']==[(15,2)]
    town=next(o for o in m.objects if o.object_id==98 and o.payload[4]==1)
    assert 'Сбор дружины Антиноя'.encode('cp1251') in town.payload
