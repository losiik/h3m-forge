import pytest

from h3m import mapfile, paths
from h3m.adventure import read_monster, read_reward
from h3m.pacing import obstacle_cells, shortest_route
from h3m.skills import inspect_hero_skills
from h3m.world import Assets
from odyssey.sirens_journey import generate
from odyssey.playable import validate


@pytest.fixture(scope='module')
def journey():
    try:files=[p for p in paths.iter_maps() if not p.name.startswith(('Odyssey-','Forge-'))]
    except paths.GameNotFoundError:pytest.skip('Native HotA references required')
    return generate(Assets.cached(files,paths.out_dir()/'world-assets.json'))


def test_ambushes_keep_two_tripled_guards_and_five_ancient_behemoths(journey):
    m,r=journey
    expected={'ismar':[(153,45),(115,9)],'lights':[(115,18),(153,30)],'sirens':[(97,5)]}
    assert len(r['ambushes'])==3
    for a in r['ambushes']:
        o=next(o for o in m.objects if o.object_id==26 and list(o.position)==a['position'])
        d=read_reward(o.payload,event=True)
        assert d['guards']==expected[a['island']]
        assert d['players']==1 and d['human'] and not d['computer'] and d['once']
        assert d['difficulties']==31 and not d['uses_scripts']
        assert not d['mana'] and not any(d['resources']) and not d['skills']
        assert d['army']==([(13,1)] if a['island']=='sirens' else [])


def test_two_hundred_sirens_keep_their_quest_id_and_trophy(journey):
    m,r=journey
    o=next(o for o in m.objects if o.object_id==54 and read_monster(o.payload)['identifier']==40002)
    d=read_monster(o.payload)
    assert m.object_templates[o.template_index].object_subid==153
    assert d['count']==200 and d['artifact']==16
    assert d['stack_count']==3 and d['upgraded_stack']==0 and d['never_grows']
    assert not any(d['resources'])
    assert r['balance']['counts']['40002']==200
    assert next(e for e in r['sea_encounters'] if e['identifier']==40002)['count']==200


def test_island_lesson_is_one_guarded_native_box_for_wisdom_and_thirty_mana(journey):
    m,r=journey
    lesson=r['sirens_lesson']
    candidates=[o for o in m.objects if o.object_id==6 and read_reward(o.payload)['skills']==[(7,3)]]
    assert len(candidates)==1
    o=candidates[0];d=read_reward(o.payload)
    assert list(o.position)==lesson['position']
    assert d['guards']==[(115,8),(153,40)] and d['mana']==30
    assert not any(d['resources']) and not d['army'] and not d['artifacts']
    assert d['difficulties']==31 and not d['uses_scripts']
    assert not d['spells'] and not any(d['primary'])
    dock=next(h['beach'] for h in r['landings']['harbours'] if h['island']=='sirens')
    x,y,z=lesson['visit']
    assert len(shortest_route(m,dock,(x,y+1,z),blocked=obstacle_cells(m),land_only=True,diagonal=False))-1<=12
    assert next(c for c in r['choices'] if c['position']==lesson['position'])['optional']
    # No repeatable well or unguarded arrival refill replaces the consumed box.
    assert not any(o.object_id==48 for o in m.objects)
    assert all(read_reward(o.payload,event=True)['mana']==0 for o in m.objects if o.object_id==26)
    assert sum(read_reward(o.payload)['mana'] for o in m.objects if o.object_id==6)==58


def test_routes_native_file_and_existing_progression_still_work(journey):
    m,r=journey
    raw=mapfile.serialize(m);parsed=mapfile.parse(raw)
    assert not parsed.tail and mapfile.serialize(parsed)==raw
    assert r['gameplay_revision']==11 and r['total_battles']==40
    assert r['landings']['checked']==16 and r['shore_access']['max_steps']<=12
    assert r['mandatory_without_optional'] and all(r['fork']['verified_alternatives'].values())
    assert r['workshop']['gold_fund']==2250 and r['finale']['growth']['enabled']
    player=next(h for h in inspect_hero_skills(parsed)['items'] if h.get('owner')==0)
    assert player['permanent_resurrection_skill_ready']
    assert next(s for s in player['skills'] if s['id']==7)['level']==2
    with pytest.raises(ValueError,match='Progression deadlock'):validate(m,r,avoid_battles={40002})
