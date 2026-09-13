from copy import deepcopy

import pytest

from h3m import mapfile, paths
from h3m.adventure import read_monster, read_reward
from h3m.authored import monster
from h3m.pacing import obstacle_cells, shortest_route
from h3m.stream import BinaryReader
from h3m.world import Assets
from odyssey.playable import validate
from odyssey.small_company import generate, START_ARMY, FINAL_ARMY


@pytest.fixture(scope='module')
def journey():
    try:
        files = [p for p in paths.iter_maps() if not p.name.startswith(('Odyssey-', 'Forge-'))]
    except paths.GameNotFoundError:
        pytest.skip('Native HotA reference templates required')
    return generate(Assets.cached(files, paths.out_dir() / 'world-assets.json'))


def hero_data(o):
    r = BinaryReader(o.payload)
    r.bytes_(6)
    if r.u8(): r.string()
    if r.u8(): r.u32()
    if r.u8(): r.u8()
    skills = [(r.u8(),r.u8()) for _ in range(r.u32())] if r.u8() else []
    assert r.u8()
    army = [(r.u16(),r.u16()) for _ in range(7)]
    r.u8()
    assert r.u8()
    slots = [(r.u16(),r.u16()) for _ in range(19)]
    r.bytes_(r.u16()*4)
    return dict(army=[u for u in army if u[0] != 65535], skills=skills, patrol=r.u8(), slots=slots)


def test_small_start_and_fixed_finale(journey):
    m,r = journey
    heroes = {o.payload[4]:hero_data(o) for o in m.objects if o.object_id==34}
    assert heroes[0]['army']==list(START_ARMY) and sum(n for _,n in START_ARMY)==16
    assert (17,2) in heroes[0]['skills'] and (7,2) in heroes[0]['skills']
    assert all(skill!=14 for skill,level in heroes[0]['skills'])
    assert heroes[0]['slots'][17][0]==0  # Spell book
    assert heroes[1]['army']==list(FINAL_ARMY) and heroes[1]['patrol']==0
    assert not r['finale']['growth']['enabled']
    assert m.victory.kind==5 and m.victory.payload==bytes(r['finale']['visit'])


def test_towns_cannot_recruit_even_after_waiting_or_ai_income_bonus(journey):
    m,_ = journey
    assert m.meta.options.hota_special_months == bytes(4)
    for o in m.objects:
        if o.object_id!=98: continue
        r=BinaryReader(o.payload)
        r.bytes_(5); assert r.u8(); r.string()
        assert r.u8()==0  # No garrison
        r.u8(); assert r.u8()==1
        built=int.from_bytes(r.bytes_(6),'little')
        forbidden=int.from_bytes(r.bytes_(6),'little')
        assert built==(1<<0 | 1<<3)
        assert built|forbidden==(1<<41)-1 and built&forbidden==0
        r.bytes_(18); r.u8(); r.bytes_(r.u32())
        assert r.u32()==0  # No town calendar events
    assert all(not e.computer_affected for e in m.events.events)


@pytest.mark.parametrize('difficulty_bit', range(5))
def test_rewards_present_and_neutral_armies_fixed_on_every_difficulty(journey, difficulty_bit):
    m,r=journey
    assert m.header.hota.allowed_difficulties_mask & (1<<difficulty_bit)
    for o in m.objects:
        if o.object_id in (6,26):
            assert read_reward(o.payload,event=o.object_id==26)['difficulties'] & (1<<difficulty_bit)
        elif o.object_id==54:
            d=read_monster(o.payload)
            assert d['count']>0 and d['never_grows'] and d['upgraded_stack']==0
            assert 1<=d['stack_count']<=d['count']
    assert r['mandatory_without_optional']  # Solver starts with zero resources


def test_resurrection_supplies_reachable_before_polyphemus(journey):
    m,r=journey
    assert not (m.meta.allowed_spells[38//8] & (1<<(38%8)))
    assert all(m.meta.allowed_spells[s//8] & (1<<(s%8)) for s in (6,7,8))  # flight / water walk / dimension door
    c=next(c for c in r['choices'] if c['position']==r['recovery']['resurrection_cache'])
    o=next(o for o in m.objects if list(o.position)==c['position'] and o.object_id==6)
    d=read_reward(o.payload)
    assert not d['guards'] and 38 in d['spells'] and d['mana']>=32
    dock=next(h['beach'] for h in r['landings']['harbours'] if h['island']=='cyclops')
    t=m.object_templates[o.template_index]; dx,dy=t.visitable_cells()[0]
    # Include monster cells: this access check cannot assume Polyphemus defeated.
    blocked=obstacle_cells(m)
    for b in m.objects:
        if b.object_id==54:
            blocked.update((b.x+x,b.y+y,b.z) for x,y in m.object_templates[b.template_index].blocked_cells())
    route=shortest_route(m,tuple(dock),(o.x+dx,o.y+dy+1,o.z),blocked=blocked,land_only=True,diagonal=False)
    assert len(route)-1<=12


def test_archangel_obtained_before_fork_without_optional_quests(journey):
    m,r=journey
    pos=r['recovery']['first_archangel']
    event=next(o for o in m.objects if o.object_id==26 and list(o.position)==pos)
    d=read_reward(event.payload,event=True)
    assert d['army']==[(13,1)] and d['once'] and not d['computer']
    trace=r['progression_trace']
    mark='ambush:'+ ', '.join(map(str,pos))
    assert trace.index(mark)<trace.index('gate:scylla')<trace.index('battle:71000')
    with pytest.raises(ValueError,match='Progression deadlock'):
        validate(m,r,avoid_ambushes={tuple(pos)})
    boxes=[c for c in r['choices'] if (13,1) in c['army']]
    assert len(boxes)==1 and boxes[0]['island']=='phaeacia' and boxes[0]['optional']
    assert boxes[0]['guards'] and all((13,1) not in c['guards'] for c in boxes)
    assert r['mandatory_without_optional']


def test_route_geometry_and_binary_survive_rebalance(journey):
    m,r=journey
    raw=mapfile.serialize(m)
    parsed=mapfile.parse(raw)
    assert not parsed.tail and mapfile.serialize(parsed)==raw
    assert r['landings']['checked']==16 and r['shore_access']['max_steps']<=12
    assert all(r['fork']['verified_alternatives'].values())
    assert len(r['training'])==12 and len(r['ambushes'])==3


@pytest.mark.parametrize('options',[dict(upgraded_stack=2),dict(stack_count=0),dict(stack_count=8),dict(stack_count=3)])
def test_invalid_fixed_monster_compositions_rejected(options):
    with pytest.raises(ValueError): monster(1,2,'Guard',65535,**options)


def test_random_monster_defaults_preserved_for_legacy_maps():
    d=read_monster(monster(1,8,'Guard',65535))
    assert d['upgraded_stack']==-1 and d['stack_count']==-1


def test_wind_island_requires_landing_and_rescue_rewards_are_not_a_toll(journey):
    from odyssey.playable import parse_quest
    m,r=journey
    info=r['wind_island']
    wind=next(o for o in m.objects if o.object_id==54 and read_monster(o.payload)['identifier']==60000)
    dx,dy=m.object_templates[wind.template_index].visitable_cells()[0]
    assert not m.terrain.tile(wind.x+dx,wind.y+dy,wind.z).is_water
    assert all(b['identifier']!=60000 for b in r['sea_encounters'])
    assert read_monster(wind.payload)['count']==4
    gate=next(g for g in r['harbour_guards'] if g['island']=='giants')
    assert gate['mission']==4 and tuple(gate['required'])==(60000,)
    with pytest.raises(ValueError,match='Progression deadlock'):
        validate(m,r,avoid_battles={60000})
    hut=next(o for o in m.objects if o.object_id==83 and list(o.position)==info['rescue_hut'])
    q=parse_quest(hut.payload,hut=True)
    assert q['mission']==4 and q['required']==(60000,)
    assert q['reward_kind']==10 and q['reward']==(3,3)
    assert any(o.object_id==48 and list(o.position)==info['well'] for o in m.objects)
    assert r['total_battles']==32 and r['sea_battles']==12
    assert r['shore_access']['max_steps']<=12 and r['landings']['checked']==16
    assert 'возвращайтесь к Эолу' not in r['objectives']['lights']
    assert r['mandatory_without_optional']
