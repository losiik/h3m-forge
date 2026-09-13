"""Real MCP messages over stdio; no game installation required."""

import json
from pathlib import Path
import sys

import pytest

pytest.importorskip("mcp")
from importlib.metadata import version
if int(version("mcp").split(".")[0]) < 2:
    pytest.skip("MCP SDK 2.x is required", allow_module_level=True)
import anyio
from mcp import Client, StdioServerParameters

from h3m import hota, mapfile


def test_stdio_discovery_read_write_and_errors(tmp_path):
    source = tmp_path / "input.h3m"
    mapfile.save(source, hota.new_map("Карта для MCP", size=72, players=2))
    original = source.read_bytes()
    from h3m.authored import hero
    from h3m.objects import ObjectTemplate
    from h3m.instances import ObjectInstance
    skill_map=hota.new_map('Навыки MCP')
    skill_map.object_templates.append(ObjectTemplate(b'TEST.def',bytes([255])*6,bytes(6),0,256,34,0,0,0,bytes(16)))
    skill_map.objects.append(ObjectInstance(4,5,0,0,bytes(5),hero(skills=((14,1),(17,2),(7,2))),34))
    skill_path=tmp_path/'skills.h3m';mapfile.save(skill_path,skill_map)
    skill_original=skill_path.read_bytes()

    async def run():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "h3m.mcp_server", "--workspace", str(tmp_path),
                  "--game-dir", str(tmp_path / "missing-game")],
            env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                 "PYTHONUTF8": "1"},
        )
        with anyio.fail_after(45):
            async with Client(params) as client:
                tools = {t.name: t for t in (await client.list_tools()).tools}
                assert len(tools) == 18
                assert tools['catalog_search'].annotations.read_only_hint
                assert tools['catalog_get'].annotations.read_only_hint
                assert 'found' in tools['catalog_get'].output_schema['properties']
                assert 'Creature' in tools['catalog_get'].output_schema['$defs']
                search=await client.call_tool('catalog_search',{'category':'artifacts','query':'защита от ослепления'})
                assert not search.is_error and search.structured_content['items'][0]['id']==101
                detail=await client.call_tool('catalog_get',{'category':'spells','id':38})
                assert not detail.is_error and detail.structured_content['item']['spell']['levels'][2]['permanent_resurrection']
                goose=await client.call_tool('catalog_get',{'category':'artifacts','id':160})
                assert not goose.is_error and goose.structured_content['item']['artifact']['effective_daily_income']['gold']==7000
                assert goose.structured_content['item']['artifact']['components']==[117,116,115]
                dragon=await client.call_tool('catalog_get',{'category':'artifacts','id':127})
                assert dragon.structured_content['item']['artifact']['effects'][0]['parameters']['limiters']==['DRAGON_NATURE']
                nymph=await client.call_tool('catalog_get',{'category':'creatures','id':153})
                assert nymph.structured_content['item']['creature']['hit_points']==4
                necropolis=await client.call_tool('catalog_search',{'category':'creatures','faction':'Некрополис'})
                assert not necropolis.is_error and necropolis.structured_content['total']==14
                monk=await client.call_tool('catalog_get',{'category':'creatures','id':8})
                assert not monk.is_error and monk.structured_content['item']['creature']['ai_value'] is None
                firebird=await client.call_tool('catalog_get',{'category':'creatures','id':130})
                assert firebird.structured_content['item']['creature']['cost']['gold']==2000
                for version,value in [('hota_1.8.0',1601),('hota_1.8.1',1672)]:
                    mammoth=await client.call_tool('catalog_get',{'category':'creatures','id':197,'ruleset':version})
                    assert mammoth.structured_content['item']['creature']['ai_value']==value
                    assert mammoth.structured_content['ruleset']==version
                absent=await client.call_tool('catalog_get',{'category':'creatures','id':65000})
                assert not absent.is_error and not absent.structured_content['found']
                assert tools['skill_catalog'].annotations.read_only_hint
                assert tools['inspect_hero_skills'].annotations.read_only_hint
                catalog=await client.call_tool('skill_catalog',{'query':'земля'})
                assert catalog.structured_content['items'][0]['id']==17
                assert catalog.structured_content['items'][0]['name_ru']=='Магия земли'
                assert catalog.structured_content['levels'][2]['key']=='advanced'
                skills=await client.call_tool('inspect_hero_skills',{'path':str(source)})
                assert skills.structured_content['items']==[] and skills.structured_content['full_parse']
                actual=await client.call_tool('inspect_hero_skills',{'path':str(skill_path)})
                assert not actual.is_error
                row=actual.structured_content['items'][0]
                assert [(s['id'],s['key'],s['level']) for s in row['skills']]==[
                    (14,'fire_magic',1),(17,'earth_magic',2),(7,'wisdom',2)]
                assert row['permanent_resurrection_skill_ready'] and row['can_learn_level_four_spells']
                assert tools['preview_map'].annotations.read_only_hint
                assert tools['inspect_texts'].annotations.read_only_hint
                assert tools["inspect_map"].annotations.read_only_hint
                assert not tools["edit_metadata"].annotations.destructive_hint
                assert "spec" in tools["generate_world"].input_schema["properties"]
                assert 'spec' in tools['generate_scenario'].input_schema['properties']
                schema=tools['generate_scenario'].input_schema
                spec_schema=next(v for v in schema['$defs'].values() if 'balance_profile' in v.get('properties',{}))
                assert spec_schema['properties']['balance_profile']['enum']==['standard','fixed']
                assert 'hero_skills' in spec_schema['properties']
                invalid_story=json.loads((Path(__file__).parents[1]/'examples/last-beacon.json').read_text('utf8'))
                invalid_story['balance_profile']='automatic_win'
                bad=await client.call_tool('generate_scenario',{'spec':invalid_story})
                assert bad.is_error
                assert tools['scenario_catalog'].annotations.read_only_hint
                resources = await client.list_resources()
                assert any(str(r.uri) == "h3m://world-example" for r in resources.resources)
                example = await client.read_resource("h3m://world-example")
                assert json.loads(example.contents[0].text)["zones"][1]["player"] == 1
                story_example=await client.read_resource('h3m://scenario-example')
                assert json.loads(story_example.contents[0].text)['finale']=='light'
                status = await client.call_tool("project_status")
                assert status.structured_content["workspace"] == str(tmp_path.resolve())
                inspected = await client.call_tool("inspect_map", {"path": str(source)})
                info = inspected.structured_content
                assert info["name"] == "Карта для MCP"
                assert info["validation"]["full_parse"]
                objects = await client.call_tool("list_objects", {"path": str(source), "limit": 1})
                assert objects.structured_content["total"] == 0
                texts = await client.call_tool('inspect_texts', {'path': str(source)})
                assert texts.structured_content['full_parse']
                assert texts.structured_content['items'] == []
                preview=await client.call_tool('preview_map',{'path':str(source),'x':4,'y':5,'width':10,'height':8,'include_grid':True})
                assert not preview.is_error
                assert preview.structured_content['tile_grid']['origin']==[4,5,0]
                assert len(preview.structured_content['tile_grid']['rows'])==8
                assert any(c.type=='image' and c.mime_type=='image/png' for c in preview.content)
                plain=await client.call_tool('preview_map',{'path':str(source),'output':'text'})
                assert not plain.is_error and not any(c.type=='image' for c in plain.content)
                changed = await client.call_tool("edit_metadata", dict(
                    path=str(source), expected_sha256=info["file_sha256"], name="Новая карта"))
                assert not changed.is_error
                target = changed.structured_content["path"]
                checked = await client.call_tool("validate_map", {"path": target})
                assert checked.structured_content["roundtrip"]
                listed = await client.call_tool("list_maps", {"limit": 1})
                assert listed.structured_content["items"][0]["path"] == target
                for tool, args in [
                    ('catalog_get',{'category':'creatures','id':True}),
                    ('catalog_search',{'category':'towns'}),
                    ('catalog_get',{'category':'creatures','id':197,'ruleset':'hota_1.9.0'}),
                    ("list_maps", {"limit": 0}),
                    ('preview_map', {'path':str(source),'x':72}),
                    ('preview_map', {'path':str(source),'include_grid':True}),
                    ("inspect_map", {"path": "../outside.h3m"}),
                    ("edit_metadata", dict(path=str(source), expected_sha256="stale", name="X")),
                    ("generate_world", {"spec": {"name": "Missing zones"}}),
                    ("generate_odyssey", {"seed": "not an integer"}),
                    ("generate_odyssey", {"seed": 42}),
                    ('inspect_hero_skills', {'path':str(skill_path),'limit':0}),
                    ('skill_catalog', {'query':17}),
                    ('generate_scenario', {'spec': {'name':'Incomplete'}}),
                ]:
                    failed = await client.call_tool(tool, args)
                    assert failed.is_error, (tool, failed)
                # Error responses must not terminate the protocol session.
                assert not (await client.call_tool("project_status")).is_error

    anyio.run(run)
    assert source.read_bytes() == original
    assert skill_path.read_bytes() == skill_original
