from copy import deepcopy
import pytest

from h3m import mapfile,paths
from h3m.adventure import read_monster,read_reward
from h3m.world import Assets
from h3m.stream import BinaryReader
from odyssey.siege_journey import generate,FINAL_ARMY
from odyssey.playable import validate,parse_quest


@pytest.fixture(scope='module')
def journey():
    try:files=[p for p in paths.iter_maps() if not p.name.startswith(('Odyssey-','Forge-'))]
    except paths.GameNotFoundError:pytest.skip('Native HotA references required')
    return generate(Assets.cached(files,paths.out_dir()/'world-assets.json'))


def test_most_battles_have_no_prize_and_none_give_gold(journey):
    m,r=journey
    infos=[read_monster(o.payload) for o in m.objects if o.object_id==54]
    assert sum(d.get('artifact',65535)!=65535 for d in infos)==7
    assert sum(d.get('artifact',65535)==65535 for d in infos)>len(infos)/2
    assert all(not d['has_message'] for d in infos if d.get('artifact',65535)==65535)
    assert all(not any(d.get('resources',())) for d in infos)
    assert all('золота' not in d['message'] and 'Награда:' not in d['message'] for d in infos)
    assert next(d for d in infos if d['identifier']==70010)['artifact']==101


def test_resurrection_has_permanent_effect_prerequisites_from_start(journey):
    # Read the shipped binary layout, not a report or the hero builder's arguments.
    m=mapfile.parse(mapfile.serialize(journey[0]))
    player=next(o for o in m.objects if o.object_id==34 and o.payload[4]==0)
    p=BinaryReader(player.payload);p.bytes_(6)
    if p.u8():p.string()
    if p.u8():p.u32()
    if p.u8():p.u8()
    assert p.u8()==1
    skills=dict((p.u8(),p.u8()) for _ in range(p.u32()))
    # Native IDs verified against VCMI config/skills.json and the player's
    # screenshot: 14 is Fire; Earth is 17. Do not import the builder's constant.
    assert skills.get(17,0)>=2  # Advanced Earth: revived troops remain after victory.
    assert 14 not in skills
    assert skills.get(7,0)>=2  # Advanced Wisdom: can learn this level-four spell.
    caches=[read_reward(o.payload) for o in m.objects if o.object_id==6]
    assert any(38 in d['spells'] for d in caches)
    assert not (m.meta.allowed_spells[38//8] & (1 << (38%8)))

    enemy=next(o for o in m.objects if o.object_id==34 and o.payload[4]==1)
    p=BinaryReader(enemy.payload);p.bytes_(6)
    if p.u8():p.string()
    if p.u8():p.u32()
    if p.u8():p.u8()
    assert p.u8()==1
    enemy_skills=dict((p.u8(),p.u8()) for _ in range(p.u32()))
    assert enemy_skills.get(17)==3 and 14 not in enemy_skills


def test_every_cache_guarded_and_no_arrival_bonuses(journey):
    m,r=journey
    for o in m.objects:
        if o.object_id==6:
            d=read_reward(o.payload)
            assert d['guards'] and not any(d['resources'])
            assert 'Награда:' not in d['message'] and 'золота' not in d['message']
        elif o.object_id==26:
            d=read_reward(o.payload,event=True)
            if not d['guards']:
                assert not any(d['resources']) and not d['army'] and not d['artifacts']
                assert not d['mana'] and not d['experience'] and not d['movement']
                assert not d['spells'] and not d['skills'] and not any(d['primary'])
            assert not d['mana']
    assert not any(o.object_id in (4,23,32,48,51,61) for o in m.objects)
    assert r['guarded_training']==4
    assert sum(read_reward(o.payload)['mana'] for o in m.objects if o.object_id==6)<=36
    huts=[parse_quest(o.payload,hut=True) for o in m.objects if o.object_id==83]
    assert all(q['mission'] in (4,5) for q in huts)
    upkeep=next(e for e in m.events.events if e.repeat_days==1)
    assert upkeep.players==1 and upkeep.human_affected and not upkeep.computer_affected
    assert int.from_bytes(upkeep.resources[-4:],'little',signed=True)==-1000


def test_archangel_is_earned_and_late_battles_are_stronger(journey):
    m,r=journey
    prize=[]
    for o in m.objects:
        if o.object_id in (6,26):
            d=read_reward(o.payload,event=o.object_id==26)
            if (13,1) in d['army']:prize.append(d)
    assert len(prize)==2 and all(d['guards'] and not d['mana'] for d in prize)
    assert r['balance']['counts']['50002']==16
    assert r['finale']['army']==FINAL_ARMY
    enemy=next(o for o in m.objects if o.object_id==34 and o.payload[4]==1)
    p=BinaryReader(enemy.payload);p.bytes_(6)
    if p.u8():p.string()
    if p.u8():p.u32()
    if p.u8():p.u8()
    if p.u8():p.bytes_(p.u32()*2)
    assert p.u8()==1
    actual=[(p.u16(),p.u16()) for _ in range(7)]
    assert tuple(u for u in actual if u[0]!=65535)==FINAL_ARMY
    p.u8();assert p.u8();p.bytes_(19*4);p.bytes_(p.u16()*4)
    assert p.u8()==1  # Can reach the adjacent town for recruitment
    assert r['mandatory_without_optional']


def test_town_waves_are_finite_but_report_does_not_claim_a_hard_cap(journey):
    m,r=journey
    town=next(o for o in m.objects if o.object_id==98 and o.payload[4]==1)
    p=BinaryReader(town.payload);p.bytes_(6);p.string();p.bytes_(2);assert p.u8()==1
    built=int.from_bytes(p.bytes_(6),'little');banned=int.from_bytes(p.bytes_(6),'little')
    assert built==sum(1<<b for b in (0,3,25,26))
    assert built|banned==(1<<41)-1
    p.bytes_(19);p.bytes_(p.u32());assert p.u32()==3
    days=[]
    for _ in range(3):
        p.string();p.string();p.bytes_(28)
        assert [p.u8(),p.u8(),p.u8()]==[2,0,1]
        days.append(p.u16()+1);assert p.u16()==0
        p.bytes_(16);assert p.u32()==31 and p.u8()==0
        p.bytes_(15);p.bytes_(6)
        assert [p.u16() for _ in range(7)]==[0,6,0,0,0,0,0]
        p.bytes_(4)
    assert days==[15,29,43] and not r['finale']['growth']['hard_cap']
    assert r['finale']['growth']['enabled']


def test_roundtrip_routes_and_wind_island_still_mandatory(journey):
    m,r=journey
    raw=mapfile.serialize(m);parsed=mapfile.parse(raw)
    assert not parsed.tail and mapfile.serialize(parsed)==raw
    assert r['landings']['checked']==16 and r['shore_access']['max_steps']<=12
    assert all(r['fork']['verified_alternatives'].values())
    with pytest.raises(ValueError,match='Progression deadlock'):
        validate(m,r,avoid_battles={60000})
