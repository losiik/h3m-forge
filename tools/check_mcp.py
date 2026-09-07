"""Exercise the installed server over real stdio, optionally building both maps."""

import argparse
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
            assert len(names) == 10, names
            results["tools"] = names
            status = await client.call_tool("project_status")
            assert not status.is_error, status
            results["status"] = status.structured_content
            if generate:
                spec = json.loads((workspace / "examples/archipelago.json").read_text("utf-8"))
                for name, arguments in [("generate_world", {"spec": spec}),
                                        ("generate_odyssey", {"seed": 20260905})]:
                    print(f"Calling {name}...", flush=True)
                    built = await client.call_tool(name, arguments, read_timeout_seconds=600)
                    assert not built.is_error, built
                    data = built.structured_content
                    checked = await client.call_tool("validate_map", {"path": data["path"]})
                    validation = checked.structured_content
                    assert validation["full_parse"] and validation["roundtrip"], validation
                    assert not validation["structural_issues"], validation
                    assert validation["file_sha256"] == data["file_sha256"]
                    if name == "generate_odyssey":
                        report = data["report"]
                        assert report["gameplay_revision"] == 4
                        assert report["pacing"]["max_steps"] <= 30
                        assert report["shore_access"]["max_steps"] <= 12
                        assert report["landings"]["checked"] == 14
                        assert len(report["bargains"]) == 3
                        assert report["no_early_island_access"]
                        assert report["no_early_sea_trials"]
                        assert report["sequential_playthrough_model"]
                        assert report["sea_battles"] == 7
                        encounters = await client.call_tool('inspect_encounters', {'path': data['path']})
                        assert not encounters.is_error, encounters
                        rows = encounters.structured_content
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
                        assert after['content']['artifact']==monster['content']['artifact']
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
