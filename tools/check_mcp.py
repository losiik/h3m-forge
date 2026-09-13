"""Exercise the installed server over real stdio, optionally building both maps."""

import argparse
import base64
import json
from pathlib import Path
import sys

import anyio
from mcp import Client, StdioServerParameters


async def check(workspace, game_dir, generate):
    args = ["-m", "h3m.mcp_server", "--workspace", str(workspace)]
    if game_dir:
        args += ["--game-dir", str(game_dir)]
    params = StdioServerParameters(command=sys.executable, args=args, env={"PYTHONUTF8": "1"})
    results = {}
    with anyio.fail_after(900):
        async with Client(params) as client:
            names = [t.name for t in (await client.list_tools()).tools]
            assert len(names) == 18, names
            catalog=await client.call_tool('catalog_get',{'category':'creatures','id':97})
            assert not catalog.is_error and catalog.structured_content['item']['key']=='ancientBehemoth'
            results['catalog_get']=catalog.structured_content
            skills=await client.call_tool('skill_catalog',{'query':'земля'})
            assert not skills.is_error and skills.structured_content['items'][0]['id']==17
            results['skill_catalog']=skills.structured_content
            results["tools"] = names
            status = await client.call_tool("project_status")
            assert not status.is_error, status
            results["status"] = status.structured_content
            if generate:
                spec = json.loads((workspace / "examples/archipelago.json").read_text("utf-8"))
                for name, arguments in [("generate_world", {"spec": spec}),
                                        ("generate_odyssey", {"seed": 20260905}),
                                        ('generate_scenario', {'spec': dict(json.loads((workspace/'examples/last-beacon.json').read_text('utf-8')),balance_profile='fixed',hero_skills=[[17,2],[7,2]])})]:
                    print(f"Calling {name}...", flush=True)
                    built = await client.call_tool(name, arguments, read_timeout_seconds=600)
                    assert not built.is_error, built
                    data = built.structured_content
                    checked = await client.call_tool("validate_map", {"path": data["path"]})
                    validation = checked.structured_content
                    assert validation["full_parse"] and validation["roundtrip"], validation
                    assert not validation["structural_issues"], validation
                    assert validation["file_sha256"] == data["file_sha256"]
                    if name in ('generate_scenario','generate_odyssey'):
                        heroes=await client.call_tool('inspect_hero_skills',{'path':data['path']})
                        assert not heroes.is_error and not heroes.structured_content['errors']
                        player=next(h for h in heroes.structured_content['items'] if h.get('owner')==0)
                        earth=next(s for s in player['skills'] if s['id']==17)
                        assert earth['name_ru']=='Магия земли' and earth['level']==2
                        assert player['permanent_resurrection_skill_ready']
                        results[name+'_hero_skills']=player
                    if name=='generate_scenario':
                        story=data['report']
                        assert story['balance']['profile']=='fixed' and story['balance']['settings_verified']
                        assert story['balance']['difficulty_levels']==[80,100,130,160,200]
                        assert not story['balance']['native_combat_verified']
                        assert story['validation']['mandatory_without_optional']
                        assert story['validation']['all_branches_completable']
                        assert 'complete:refuge' not in story['validation']['mandatory_trace']
                        assert Path(data['walkthrough_path']).is_file()
                        catalog=await client.call_tool('scenario_catalog',{'limit':10})
                        assert not catalog.is_error and catalog.structured_content['creatures']['total']>10
                        results['scenario_walkthrough']=data['walkthrough_path']
                    if name == "generate_odyssey":
                        report = data["report"]
                        assert report["gameplay_revision"] == 12
                        assert report['finale']['growth']['enabled']
                        assert report['balance']['difficulty_levels'] == [80,100,130,160,200]
                        assert report["pacing"]["max_steps"] <= 30
                        assert report["shore_access"]["max_steps"] <= 12
                        assert report["landings"]["checked"] == 16
                        assert report["landscape_revision"] == 2
                        assert report['guidance']['revision'] == 2
                        assert report['crown_dependency_removed'] and report['mandatory_without_optional']
                        text_check = await client.call_tool('inspect_texts', {'path': data['path'], 'limit': 200})
                        assert not text_check.is_error, text_check
                        assert not text_check.structured_content['errors']
                        assert not any('КУРС:' in t['text'] for t in text_check.structured_content['items'])
                        assert report["barriers"]["revision"] == 2 and report["barriers"]["blocked_land_cells"]
                        assert not report["bargains"]
                        assert report['guarded_training'] == 4 and len(report['ambushes']) == 3
                        assert report['finale']['owner'] == 1
                        assert all(report['fork']['verified_alternatives'].values())
                        assert report["no_early_island_access"]
                        assert report["no_early_sea_trials"]
                        assert report["sequential_playthrough_model"]
                        assert report["sea_battles"] == 12
                        assert report['reward_policy']['monster_gold'] == 0
                        assert report['reward_policy']['total_cache_mana'] == 58
                        preview = await client.call_tool('preview_map', {'path':data['path'],'limit':10})
                        assert not preview.is_error and preview.structured_content['file_sha256']==data['file_sha256']
                        picture=next(c for c in preview.content if c.type=='image')
                        assert picture.mime_type=='image/png'
                        preview_file=workspace/'out/mcp-odyssey-preview.png'
                        preview_file.write_bytes(base64.b64decode(picture.data))
                        results['preview_map']=dict(path=str(preview_file),file_sha256=data['file_sha256'])
                        encounters = await client.call_tool('inspect_encounters', {'path': data['path'],'limit':200})
                        assert not encounters.is_error, encounters
                        rows = encounters.structured_content
                        sirens=next(x for x in rows['items'] if x['object_id']==54 and x['content']['identifier']==40002)
                        assert sirens['content']['count']==200
                        lesson=next(x for x in rows['items'] if x['position']==report['sirens_lesson']['position'] and x['object_id']==6)
                        assert lesson['content']['skills']==[[7,3]] and lesson['content']['mana']==30
                        assert lesson['content']['guards'] and lesson['content']['difficulties']==31
                        assert report['total_battles']==41
                        well_guard=next(x for x in rows['items'] if x['object_id']==26 and x['position']==report['well_trial']['guard_position'])
                        assert well_guard['content']['guards']==[[143,30],[142,15]]
                        assert well_guard['content']['mana']==0 and report['well_trial']['object_id']==49
                        assert report['well_trial']['access']['no_bypass'] and report['well_trial']['optional_verified']
                        monster = next(x for x in rows['items'] if x['object_id']==54)
                        edited = await client.call_tool('edit_monster', dict(
                            path=data['path'], expected_sha256=data['file_sha256'],
                            object_index=monster['index'], count=monster['content']['count']+1,
                            message='Проверка редактирования через MCP'))
                        assert not edited.is_error, edited
                        changed = await client.call_tool('inspect_encounters', {'path': edited.structured_content['path']})
                        after = next(x for x in changed.structured_content['items'] if x['index']==monster['index'])
                        assert after['content']['count']==monster['content']['count']+1
                        assert after['content']['identifier']==monster['content']['identifier']
                        assert after['content'].get('artifact',65535)==monster['content'].get('artifact',65535)
                        assert after['content']['message']=='Проверка редактирования через MCP'
                        unchanged = await client.call_tool('inspect_map', {'path': data['path']})
                        assert unchanged.structured_content['file_sha256']==data['file_sha256']
                        results['edit_monster'] = edited.structured_content['path']
                    results[name] = {key: data[key] for key in
                                     ("path", "report_path", "file_sha256")}
                    results[name]["validation"] = validation
                    print(data["path"], flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--game-dir", type=Path)
    parser.add_argument("--generate", action="store_true", help="Build world and Odyssey bundles")
    args = parser.parse_args()
    results = anyio.run(check, args.workspace.resolve(), args.game_dir, args.generate)
    output = args.workspace / "out/mcp-smoke.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"MCP check passed: {output.resolve()}")


if __name__ == "__main__":
    main()
