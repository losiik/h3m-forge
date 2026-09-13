from copy import deepcopy
from pathlib import Path
import importlib.util
import sys
import pytest
from h3m.game_catalog import catalog_get,catalog_search


def artifact(i):return catalog_get('artifacts',i)['item']['artifact']


def test_complete_artifact_identities_and_assembly_graph():
    rows=catalog_search('artifacts',limit=200)['items']
    assert {r['id'] for r in rows}==set(range(166))-{144,145}
    assert sum(bool(artifact(r['id'])['components']) for r in rows)==16
    assert all(artifact(r['id'])['components'] is not None for r in rows)
    assert catalog_get('artifacts',146)['item']['name_ru']=='Пушка'
    assert catalog_get('creatures',146)['found'] is False
    assert catalog_search('artifacts',tag='сборный')['total']==16


def test_combination_totals_are_not_double_counted():
    a=artifact(129)
    assert a['components']==[31,32,33,34,35,36]
    assert a['effective_primary_skills']==dict(attack=21,defence=21,spellpower=21,knowledge=21)
    assert artifact(134)['assembly_slots']['ring']==2
    assert artifact(134)['effective_primary_skills']['attack']==16
    assert artifact(143)['effective_primary_skills']==dict(attack=5,defence=5,spellpower=4,knowledge=4)
    goose=artifact(160)
    assert goose['effective_daily_income']['gold']==7000
    assert goose['assembly_slots']=={'misc':3}
    assert next(e for e in goose['effects'] if e['type']=='GENERATE_RESOURCE')['value']==4750
    assert sum(e['value'] for e in goose['component_effects'] if e['type']=='GENERATE_RESOURCE')==2250
    assert goose['effects_include_components'] is False
    assert artifact(140)['effective_daily_income']['mercury']==5
    assert all(e['source_artifact_id'] in a['components'] for e in a['component_effects'])


def test_conditioned_effects_and_hota_differences():
    # Dragon Blood strengthens dragons, not the hero's four base skills.
    assert artifact(127)['effective_primary_skills']==dict(attack=0,defence=0,spellpower=0,knowledge=0)
    assert artifact(127)['effects'][0]['parameters']['limiters']==['DRAGON_NATURE']
    assert artifact(4)['cost_gold']==1500
    assert next(e for e in artifact(70)['effects'] if e['type']=='MOVEMENT')['value']==200
    assert next(e for e in artifact(98)['effects'] if e['type']=='MOVEMENT')['value']==400
    assert artifact(130)['default_availability']=='assembly_disabled_by_default'
    assert artifact(142)['default_availability']=='disabled_on_random_maps_by_default'
    assert next(e for e in artifact(125)['effects'] if e['type']=='BATTLE_CAN_FLEE')['parameters']['requires_heroes_on_both_sides']
    assert artifact(147)['slot']==['right_hand'] and artifact(147)['effective_primary_skills']['attack']==7
    assert artifact(146)['slot']==artifact(4)['slot']
    assert 158 in [r['id'] for r in catalog_search('artifacts',query='воскрешение')['items']]


def test_sources_and_unknown_anchor_are_honest():
    get=catalog_get('artifacts',143)
    assert {'art-native','art-docs','art-vcmi','art-table'}<=set(get['item']['source_ids'])
    old=catalog_get('artifacts',129)['item']
    assert old['artifact']['slot']==[]
    assert any('artifact.slot:' in s for s in old['verification']['unknown_fields'])
    assert old['artifact']['assembly_slots']['right_hand']==1
    assert any(s['kind']=='community_reference' for s in catalog_get('artifacts',11)['sources'])


@pytest.fixture
def importer(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'tools'))
    import build_artifact_catalog
    return build_artifact_catalog


def test_corrupted_native_records_fail(importer):
    with pytest.raises(ValueError):importer.native_artifacts(b'')
    with pytest.raises(ValueError):importer.native_artifacts(b'\x06\x00\x00\x00art141\xff\xff\xff\x7f')


def test_assembly_cycle_and_missing_component_fail(importer):
    one=deepcopy(catalog_get('artifacts',11)['item'])
    one['artifact']['components']=[11]
    with pytest.raises(ValueError,match='Cyclic'):importer.finalize([one])
    one['artifact']['components']=[999]
    with pytest.raises(ValueError,match='Unknown'):importer.finalize([one])


def test_table_parser_treats_markup_as_data(importer):
    p=importer.Tables();p.feed('<table><tr><td>Меч <b>огня</b></td><td>7</td></tr></table>')
    assert p.rows==[['Меч огня','7']]
