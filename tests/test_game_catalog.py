import re
import pytest
from h3m.game_catalog import catalog_get, catalog_search
from h3m.service import MapService


def test_search_by_russian_effect_english_alias_and_id():
    assert [r['id'] for r in catalog_search('artifacts','защита от ослепления')['items']]==[101]
    assert [r['id'] for r in catalog_search('creatures','Ancient Behemoth')['items']]==[97]
    assert [r['id'] for r in catalog_search('creatures','Птицы Грома')['items']]==[93]
    assert [r['id'] for r in catalog_search('spells','38')['items']]==[38]
    assert catalog_search('creatures',faction='castle',tag='ranged')['total']==4


def test_actual_properties_distinguish_behemoth_from_thunderbird():
    b=catalog_get('creatures',97)['item'];t=catalog_get('creatures',93)['item']
    assert b['key']=='ancientBehemoth' and b['creature']['hit_points']==300
    assert t['key']=='thunderbird' and t['creature']['hit_points']==60
    assert any(e['type']=='ENEMY_DEFENCE_REDUCTION' and e['value']==80 for e in b['creature']['effects'])
    assert b['scenario_support']['status']=='requires_reference_template'
    assert catalog_get('creatures',142)['item']['name_ru']=='Кочевник'
    assert catalog_get('creatures',143)['item']['name_ru']=='Вор'


def test_artifact_slots_effects_and_compiler_restriction():
    sword=catalog_get('artifacts',11)['item'];pendant=catalog_get('artifacts',101)['item']
    assert sword['artifact']['slot']==['right_hand'] and sword['artifact']['cost_gold']==6000
    assert sword['artifact']['effects'][0]['value']==6
    assert sword['scenario_support']['status']=='supported'
    assert pendant['artifact']['slot']==['neck']
    assert pendant['artifact']['effects'][0]['subtype']=='blind'
    assert pendant['scenario_support']['status']=='unsupported'
    assert pendant['artifact']['components']==[]


def test_resurrection_levels_and_prerequisites_are_explicit():
    r=catalog_get('spells',38)['item']['spell']
    assert r['level']==4 and r['schools']==['earth']
    assert [v['mana_cost'] for v in r['levels']]==[20,16,16,16]
    assert [v['permanent_resurrection'] for v in r['levels']]==[False,False,True,True]
    assert r['levels'][2]['formula']=='50 * spell_power + 80'
    assert any(p['skill_id']==17 and p['minimum_level']==2 for p in r['prerequisites'])
    haste=catalog_get('spells',53)['item']['spell']
    assert [v['mass'] for v in haste['levels']]==[False,False,False,True]


def test_unknown_is_not_fabricated_and_ids_have_separate_namespaces():
    assert catalog_get('creatures',65000)['found'] is False
    assert catalog_get('creatures',65000)['item'] is None
    assert catalog_get('artifacts',144)['found'] is False
    assert catalog_get('creatures',97)['found'] is True


def test_all_cards_have_pinned_provenance_and_explicit_hota_limits():
    result=catalog_search(limit=200)
    assert result['coverage']=={'creatures':189,'artifacts':164,'spells':8}
    for row in result['items']+catalog_search(limit=200,offset=200)['items']:
        result=catalog_get(row['category'],row['id']);item=result['item']
        assert item['verification']['hota_runtime']=='not_verified'
        if item['verification']['properties']!='official_documentation_and_native_data':
            assert item['reference_ruleset']!=item['target_ruleset']
        else:
            assert item['reference_ruleset']==item['target_ruleset']=='hota_1.8.1'
        assert sum(item[k] is not None for k in ('creature','artifact','spell'))==1
        assert {s['id'] for s in result['sources']}==set(item['source_ids'])
        for s in result['sources']:
            assert re.fullmatch('[0-9a-f]{64}',s['sha256'])
            if s['kind']=='vcmi':
                assert re.fullmatch('[0-9a-f]{40}',s['revision']) and s['revision'] in s['location']


def test_pagination_copy_isolation_and_service_without_game(tmp_path):
    service=MapService(tmp_path,tmp_path/'missing-game')
    ids=[];offset=0
    while True:
        r=service.catalog_search(limit=7,offset=offset)
        ids.extend((v['category'],v['id']) for v in r['items'])
        if r['next_offset'] is None:break
        offset=r['next_offset']
    assert len(ids)==len(set(ids))==361
    assert not list(tmp_path.iterdir())
    data=service.catalog_get('creatures',97);data['item']['creature']['hit_points']=0
    assert service.catalog_get('creatures',97)['item']['creature']['hit_points']==300
    assert catalog_search(offset=10000)['items']==[]


@pytest.mark.parametrize('kwargs',[{'category':'towns'},{'limit':0},{'limit':True},{'offset':-1},{'query':12},{'query':'x'*257},{'ruleset':'hota_1.9.0'}])
def test_invalid_search_inputs(kwargs):
    with pytest.raises(ValueError):catalog_search(**kwargs)


@pytest.mark.parametrize('value',[-1,True,'97',65535])
def test_invalid_get_ids(value):
    with pytest.raises(ValueError):catalog_get('creatures',value)


def test_hota_factions_identities_and_resources():
    assert catalog_search(faction='cove')['total']==15
    assert catalog_search(faction='factory')['total']==16
    assert catalog_search(faction='bulwark')['total']==14
    n=catalog_get('creatures',153)['item']
    assert n['name_ru']=='Нимфа' and n['creature']['hit_points']==4
    assert n['creature']['attack']==5 and n['creature']['cost']['gold']==35
    assert catalog_get('creatures',160)['item']['key']=='ayssid'
    assert catalog_get('creatures',166)['item']['key']=='haspid'
    assert catalog_get('creatures',166)['item']['creature']['cost']['sulfur']==2
    assert catalog_get('creatures',183)['item']['creature']['cost']['crystal']==1
    assert catalog_get('creatures',199)['item']['creature']['cost']['gems']==1
    assert catalog_get('creatures',138)['item']['creature']['upgrades']==[171]
    assert catalog_get('creatures',158)['item']['creature']['upgrades']==[151]
    assert catalog_get('creatures',150)['found'] is False  # War machine, not a regular troop.
    assert catalog_get('creatures',152)['found'] is False  # Technical tower.


def test_explicit_version_changes_and_no_cross_profile_mutation():
    a=catalog_get('creatures',197,'hota_1.8.0')
    b=catalog_get('creatures',197)
    assert a['ruleset']=='hota_1.8.0' and b['ruleset']=='hota_1.8.1'
    for field in ('fight_value','ai_value'):
        assert a['item']['creature'][field]==1601
        assert b['item']['creature'][field]==1672
    assert b['item']['version_notes']
    a['item']['creature']['ai_value']=0
    assert catalog_get('creatures',197,'hota_1.8.0')['item']['creature']['ai_value']==1601
    assert catalog_search(faction='bulwark',ruleset='hota_1.8.0')['items'][0]['reference_ruleset']=='hota_1.8.0'
    with pytest.raises(ValueError):catalog_get('creatures',197,'latest')


def test_all_profiles_match_explicit_output_schema():
    from h3m.catalog_contract import GetResult, SearchResult
    for version in ('hota_1.8.0','hota_1.8.1'):
        result=catalog_search(limit=200,ruleset=version)
        SearchResult.model_validate(result)
        rows=result['items']+catalog_search(limit=200,offset=200,ruleset=version)['items']
        assert len(rows)==361
        for row in rows:
            GetResult.model_validate(catalog_get(row['category'],row['id'],version))


def test_mechanics_search_and_reference_only_base_values():
    assert catalog_search('creatures',query='ремонт',faction='factory')['total']>=4
    a=catalog_get('creatures',176)['item']
    assert any(e['type']=='MECHANICAL' for e in a['creature']['effects'])
    assert a['verification']['unknown_fields']
    assert catalog_get('creatures',97)['item']['verification']['properties']=='reference_only'


def test_all_original_factions_and_russian_filters():
    from h3m.game_catalog import FACTIONS
    original=('castle','rampart','tower','inferno','necropolis','dungeon','stronghold','fortress','conflux')
    for faction in original:
        result=catalog_search('creatures',faction=faction,limit=200)
        assert result['total']==14
        assert catalog_search('creatures',faction=FACTIONS[faction])['items']==result['items']
        cards=[catalog_get('creatures',r['id'])['item']['creature'] for r in result['items']]
        assert sorted(c['level'] for c in cards)==[level for level in range(1,8) for _ in range(2)]
    assert catalog_search('creatures',faction='neutral')['total']==18
    ids=[r['id'] for r in catalog_search('creatures',limit=200)['items']]
    assert len(ids)==len(set(ids))==189
    assert set(range(200))-set(ids)=={122,124,126,128,145,146,147,148,149,150,152}


def test_golem_identity_is_not_inferred_from_historical_vcmi_key():
    stone=catalog_get('creatures',32)['item'];iron=catalog_get('creatures',33)['item']
    assert stone['name_en']=='Stone Golem' and stone['key']=='stoneGolem'
    assert iron['name_en']=='Iron Golem' and iron['key']=='ironGolem'
    assert stone['creature']['upgrades']==[33]
    assert stone['creature']['speed']==3 and iron['creature']['speed']==5


def test_original_creature_hota_deltas_and_unknown_ai():
    for version in ('hota_1.8.0','hota_1.8.1'):
        get=lambda i:catalog_get('creatures',i,version)['item']
        for i,gold in ((120,950),(121,1200),(130,2000),(131,3000)):
            assert get(i)['creature']['cost']['gold']==gold
        for i in (130,131):
            assert get(i)['creature']['growth']==1
            assert get(i)['creature']['horde_growth']==1
        fire=get(130)
        assert not any(e['type']=='SPELL_SCHOOL_IMMUNITY' and e['subtype']=='fire' for e in fire['creature']['effects'])
        assert any(e['type']=='SPELL_DAMAGE_REDUCTION' and e['value']==50 for e in fire['creature']['effects'])
        assert any(e['type']=='LUCK' and e['value']==-2 for e in get(55)['creature']['effects'])
        assert get(100)['creature']['ai_value']==151
        assert get(101)['creature']['fight_value']==174
        assert get(53)['creature']['ai_value']==2343
        assert get(137)['creature']['map_amount_min']==10
        for i in (8,38,69,81,82,95,130,134):
            card=get(i)
            assert card['creature']['ai_value'] is None
            assert any('creature.ai_value:' in u for u in card['verification']['unknown_fields'])
            assert card['verification']['properties']=='reference_with_documented_hota_changes'
