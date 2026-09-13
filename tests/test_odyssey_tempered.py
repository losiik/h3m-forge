import pytest

from h3m import mapfile, paths
from h3m.adventure import read_reward, read_monster
from h3m.pacing import obstacle_cells, shortest_route
from h3m.skills import inspect_hero_skills
from h3m.world import Assets
from odyssey.tempered_journey import generate
from odyssey.playable import parse_quest, validate


@pytest.fixture(scope='module')
def journey():
    try:files=[p for p in paths.iter_maps() if not p.name.startswith(('Odyssey-','Forge-'))]
    except paths.GameNotFoundError:pytest.skip('Native HotA reference templates required')
    return generate(Assets.cached(files,paths.out_dir()/'world-assets.json'))


def test_mixed_guards_and_ambushes_strengthened_without_more_loot(journey):
    m,r=journey
    assert len(r['balance']['early_revision']['boxes'])==13
    for c in r['choices']:
        o=next(o for o in m.objects if o.object_id==6 and list(o.position)==c['position'])
        d=read_reward(o.payload)
        assert tuple(d['guards'])==tuple(c['guards'])
        if c['island']=='cyclops':assert tuple(d['guards'])==((0,10),(2,4))
        if c['island']=='aeolus':assert tuple(d['guards'])==((26,2),)  # Keep the dragon challenge.
    for a in r['ambushes']:
        o=next(o for o in m.objects if o.object_id==26 and list(o.position)==a['position'])
        d=read_reward(o.payload,event=True)
        assert d['human'] and not d['computer'] and d['once']
        assert not d['mana'] and not any(d['resources'])
        if a['island']=='ismar':assert tuple(d['guards'])==((153,15),(115,3)) and not d['army']
        if a['island']=='sirens':assert tuple(d['guards'])==((97,6),) and tuple(d['army'])==((13,1),)
    monsters={d['identifier']:d for d in (read_monster(o.payload) for o in m.objects if o.object_id==54)}
    assert monsters[50000]['count']==16 and monsters[50001]['count']==8
    assert monsters[70010]['count']==1  # Preserve the player's liked Cyclops fight.
    assert all(not any(d.get('resources',())) for d in monsters.values())


def test_sword_is_available_before_dragons_and_no_orb_dependency_remains(journey):
    m,r=journey
    q=next(q for q in r['quests'] if q['island']=='aeolus')
    o=next(o for o in m.objects if o.object_id==83 and list(o.position)==q['position'])
    actual=parse_quest(o.payload,hut=True)
    assert actual['mission']==4 and actual['required']==(40000,) and actual['reward']==11
    dock=next(h['beach'] for h in r['landings']['harbours'] if h['island']=='aeolus')
    dx,dy=m.object_templates[o.template_index].visitable_cells()[0]
    dragon=next(c for c in r['choices'] if c['island']=='aeolus')
    blocked=obstacle_cells(m)|{tuple(dragon['position'])}
    assert shortest_route(m,dock,(o.x+dx,o.y+dy+1,o.z),blocked=blocked,land_only=True)
    huts=[parse_quest(o.payload,hut=True) for o in m.objects if o.object_id==83]
    assert not any(q['mission']==5 and 79 in q['required'] for q in huts)
    assert not any(q['mission']==5 and 11 in q['required'] for q in huts)
    calypso=next(q for q in r['quests'] if q['island']=='calypso')
    assert calypso['mission']==4 and calypso['required']==(70019,)


def test_early_native_workshop_and_one_guarded_purchase_budget(journey):
    m,r=journey
    factories=[o for o in m.objects if o.object_id==106]
    assert len(factories)==1 and factories[0].payload==b''
    f=factories[0];t=m.object_templates[f.template_index]
    assert t.animation_file.lower()==b'avgsieg0.def'
    assert r['workshop']['island']=='troy'
    town=next(o for o in m.objects if o.object_id==98 and o.payload[4]==0)
    assert f.position!=town.position
    positives=[]
    for o in m.objects:
        if o.object_id!=6:continue
        d=read_reward(o.payload)
        if any(d['resources']):positives.append((o,d))
    assert len(positives)==1
    o,d=positives[0]
    assert tuple(d['resources'])==(0,0,0,0,0,0,2250) and d['guards']
    assert d['difficulties']==31
    assert 2250==sum(r['workshop']['prices'].values())  # Independent of starting treasury.
    assert next(c for c in r['choices'] if tuple(c['position'])==o.position)['island']=='troy'
    # Both purchasing and earning funds are reachable from the start island's beach.
    dock=next(h['beach'] for h in r['landings']['harbours'] if h['island']=='troy')
    for obj in (f,o):
        dx,dy=m.object_templates[obj.template_index].visitable_cells()[0]
        assert shortest_route(m,dock,(obj.x+dx,obj.y+dy+1,0),blocked=obstacle_cells(m),land_only=True)


def test_native_roundtrip_routes_skills_and_late_balance_preserved(journey):
    m,r=journey
    raw=mapfile.serialize(m);parsed=mapfile.parse(raw)
    assert not parsed.tail and mapfile.serialize(parsed)==raw
    assert r['gameplay_revision']==10 and r['landings']['checked']==16
    assert r['shore_access']['max_steps']<=12 and r['mandatory_without_optional']
    assert all(r['fork']['verified_alternatives'].values())
    player=next(h for h in inspect_hero_skills(parsed)['items'] if h.get('owner')==0)
    assert player['permanent_resurrection_skill_ready'] and player['can_learn_level_four_spells']
    assert r['reward_policy']['total_cache_mana']==28 and r['finale']['growth']['enabled']
    with pytest.raises(ValueError,match='Progression deadlock'):validate(m,r,avoid_battles={60000})
