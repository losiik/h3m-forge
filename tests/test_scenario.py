from copy import deepcopy
import json
from pathlib import Path

import pytest

from h3m import authored, mapfile, paths
from h3m.scenario import generate_scenario
from h3m.scenario_spec import ScenarioSpec
from h3m.scenario_audit import audit_scenario
from h3m.world import Assets


def design():
    return json.loads((Path(__file__).parents[1]/'examples/last-beacon.json').read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def assets():
    try:files=[p for p in paths.iter_maps() if not p.name.startswith(('Odyssey-Homecoming','Forge-'))]
    except paths.GameNotFoundError:pytest.skip('Native references required')
    return Assets.cached(files,paths.out_dir()/'world-assets.json')


@pytest.fixture(scope='module')
def beacon(assets):
    return generate_scenario(ScenarioSpec.from_dict(design()),assets)


def test_arbitrary_story_finishes_without_optional_branch_or_rewards(beacon):
    m,r=beacon
    assert m.header.name_text=='Последний маяк'
    assert r['validation']['mandatory_without_optional']
    assert 'complete:refuge' not in r['validation']['mandatory_trace']
    assert 'complete:refuge' in r['validation']['all_branches_trace']
    assert r['validation']['all_branches_trace'][-1]=='complete:beacon'
    assert r['landings']['checked']==5 and r['pacing']['max_steps']<=65
    assert mapfile.serialize(m)==mapfile.serialize(mapfile.parse(mapfile.serialize(m)))


@pytest.mark.parametrize('change,match',[
    (lambda s:s['chapters'][0].update(requires=['beacon']), 'starting chapter'),
    (lambda s:s['chapters'][-1].update(requires=['refuge']), 'optional'),
    (lambda s:s['chapters'][-1].update(requires=['missing']), 'prerequisite'),
    (lambda s:s.update(spells=[6]), 'combat spells'),
    (lambda s:s.update(army=[[1,True]]), 'integer'),
    (lambda s:s.update(misspelled='silently ignored'), 'specification'),
    (lambda s:s['chapters'][0].update(reward={'artifacts':[72]}), '10..51'),
])
def test_bad_designs_rejected_before_loading_game(change,match):
    s=design();change(s)
    with pytest.raises(ValueError,match=match):ScenarioSpec.from_dict(s)


def test_fixed_balance_profile_is_optional_and_strict():
    s=design()
    assert ScenarioSpec.from_dict(s).balance_profile=='standard'
    for invalid in ('auto',True,[],None):
        with pytest.raises(ValueError,match='balance_profile'):
            ScenarioSpec.from_dict(dict(s,balance_profile=invalid))


def test_custom_starting_skills_survive_scenario_generation(assets):
    from h3m.skills import inspect_hero_skills
    spec=ScenarioSpec.from_dict(dict(design(),hero_skills=[[17,2],[7,2]],spells=[38]))
    m,r=generate_scenario(spec,assets)
    rows=inspect_hero_skills(mapfile.parse(mapfile.serialize(m)))['items']
    player=next(h for h in rows if h.get('owner')==0)
    assert [(s['id'],s['level']) for s in player['skills']]==[(17,2),(7,2)]
    assert player['permanent_resurrection_skill_ready'] and player['can_learn_level_four_spells']
    assert r['specification']['hero_skills']==[[17,2],[7,2]]


@pytest.mark.parametrize('value', [[[17,2],[17,3]],[[17,0]],[[250,2]],[[17,True]]])
def test_scenario_rejects_invalid_starting_skills(value):
    with pytest.raises(ValueError,match='hero_skills'):
        ScenarioSpec.from_dict(dict(design(),hero_skills=value))


def test_fixed_story_profile_preserves_rewards_and_disables_random_growth(beacon):
    from h3m.adventure import read_monster, read_reward
    from h3m.balance import apply_fixed_profile
    from h3m.stream import BinaryReader
    original,r=beacon
    m=deepcopy(original)
    before=[o.payload for o in m.objects if o.object_id in (6,26)]
    profile=apply_fixed_profile(m)
    assert profile['difficulty_levels']==[80,100,130,160,200]
    assert profile['settings_verified'] and not profile['native_combat_verified']
    assert before==[o.payload for o in m.objects if o.object_id in (6,26)]
    for o in m.objects:
        if o.object_id==54:
            d=read_monster(o.payload)
            assert d['never_grows'] and d['upgraded_stack']==0 and d['stack_count']>=1
        elif o.object_id in (6,26):
            assert read_reward(o.payload,event=o.object_id==26)['difficulties']==31
        elif o.object_id==98:
            p=BinaryReader(o.payload);p.bytes_(6);p.string();p.bytes_(2)
            assert p.u8()==1
            built=int.from_bytes(p.bytes_(6),'little')
            banned=int.from_bytes(p.bytes_(6),'little')
            assert built==(1<<0 | 1<<3) and built|banned==(1<<41)-1
            p.bytes_(19);p.bytes_(p.u32());assert p.u32()==0
    assert m.meta.options.hota_special_months==bytes(4)
    assert mapfile.serialize(mapfile.parse(mapfile.serialize(m)))==mapfile.serialize(m)
    assert audit_scenario(m,r)['mandatory_without_optional']
    assert original.meta.options.hota_special_months!=bytes(4)


def test_fixed_profile_compiles_through_public_spec(assets):
    s=design();s['balance_profile']='fixed'
    m,r=generate_scenario(ScenarioSpec.from_dict(s),assets)
    assert r['balance']['profile']=='fixed' and r['balance']['settings_verified']
    assert r['specification']['balance_profile']=='fixed'
    assert r['validation']['mandatory_without_optional']


def test_fixed_profile_rejects_partial_difficulty_rewards_before_mutating(beacon):
    from h3m.balance import apply_fixed_profile
    from h3m.adventure import Reward
    m=deepcopy(beacon[0])
    o=next(o for o in m.objects if o.object_id==6)
    payload=Reward('Only easy').pandora()
    # HotA final extension: mode, movement, difficulty mask, script flag.
    o.payload=payload[:-5]+(1).to_bytes(4,'little')+payload[-1:]
    before=mapfile.serialize(m)
    with pytest.raises(ValueError,match='all five difficulties'):apply_fixed_profile(m)
    assert mapfile.serialize(m)==before


def test_cycle_inside_otherwise_rooted_graph_rejected():
    s=design();s['chapters'][1]['requires']=['workshop']
    with pytest.raises(ValueError,match='cycle'):ScenarioSpec.from_dict(s)


def test_depleted_mandatory_supply_is_rejected(assets):
    s=design();s['chapters'][2]['challenge']['auto_supply']=False
    with pytest.raises(ValueError,match='deadlock'):generate_scenario(ScenarioSpec.from_dict(s),assets)


def test_mutated_completion_condition_rejected(beacon):
    original,r=beacon;m=deepcopy(original)
    pos=next(tuple(g['position']) for g in r['gates'] if g['chapter']=='workshop' and g['role']=='completion')
    next(o for o in m.objects if o.position==pos and o.object_id==215).payload=authored.quest((0,),'Skip','Skip',mission=8)
    with pytest.raises(ValueError,match='Completion condition changed'):audit_scenario(m,r)


def test_missing_coastal_walls_really_exposes_future_chapters(beacon):
    original,r=beacon;m=deepcopy(original)
    m.objects=[o for o in m.objects if o.object_id not in (147,161)]
    with pytest.raises(ValueError,match='bypass|before entry'):audit_scenario(m,r)


def test_merging_branches_and_consumptive_quests(assets):
    s=dict(name='Совет трёх',description='Соберите союзников перед советом.',finale='council',chapters=[
        dict(id='camp',title='Лагерь',text='Начало переговоров.',reward=dict(artifacts=[40])),
        dict(id='guard',title='Стража',text='Помогите гарнизону.',requires=['camp'],terrain='snow',
             challenge=dict(kind='army',army=[[0,6]],text='Оставьте шесть копейщиков в гарнизоне.')),
        dict(id='relic',title='Святилище',text='Отдайте дар совета.',requires=['camp'],terrain='lava',
             challenge=dict(kind='artifacts',artifacts=[40],auto_supply=False,text='Передайте дар из лагеря.')),
        dict(id='council',title='Совет',text='Две делегации должны прибыть.',requires=['guard','relic'],terrain='wasteland')])
    m,r=generate_scenario(ScenarioSpec.from_dict(s),assets)
    trace=r['validation']['mandatory_trace']
    assert trace.index('complete:guard')<trace.index('gate:council:entry')
    assert trace.index('complete:relic')<trace.index('gate:council:entry')
    assert len({t['artifact'] for t in r['tokens']})==4


def test_seed_is_repeatable_and_changes_scenery(assets,beacon):
    s=design();m,r=generate_scenario(ScenarioSpec.from_dict(s),assets)
    assert mapfile.serialize(m)==mapfile.serialize(beacon[0])
    s['seed']+=1;m2,r2=generate_scenario(ScenarioSpec.from_dict(s),assets)
    assert mapfile.serialize(m)!=mapfile.serialize(m2)
    assert r2['validation']['mandatory_without_optional']
