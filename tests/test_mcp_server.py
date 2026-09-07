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
                assert len(tools) == 10
                assert tools["inspect_map"].annotations.read_only_hint
                assert not tools["edit_metadata"].annotations.destructive_hint
                assert "spec" in tools["generate_world"].input_schema["properties"]
                resources = await client.list_resources()
                assert any(str(r.uri) == "h3m://world-example" for r in resources.resources)
                example = await client.read_resource("h3m://world-example")
                assert json.loads(example.contents[0].text)["zones"][1]["player"] == 1
                status = await client.call_tool("project_status")
                assert status.structured_content["workspace"] == str(tmp_path.resolve())
                inspected = await client.call_tool("inspect_map", {"path": str(source)})
                info = inspected.structured_content
                assert info["name"] == "Карта для MCP"
                assert info["validation"]["full_parse"]
                objects = await client.call_tool("list_objects", {"path": str(source), "limit": 1})
                assert objects.structured_content["total"] == 0
                changed = await client.call_tool("edit_metadata", dict(
                    path=str(source), expected_sha256=info["file_sha256"], name="Новая карта"))
                assert not changed.is_error
                target = changed.structured_content["path"]
                checked = await client.call_tool("validate_map", {"path": target})
                assert checked.structured_content["roundtrip"]
                listed = await client.call_tool("list_maps", {"limit": 1})
                assert listed.structured_content["items"][0]["path"] == target
                for tool, args in [
                    ("list_maps", {"limit": 0}),
                    ("inspect_map", {"path": "../outside.h3m"}),
                    ("edit_metadata", dict(path=str(source), expected_sha256="stale", name="X")),
                    ("generate_world", {"spec": {"name": "Missing zones"}}),
                    ("generate_odyssey", {"seed": "not an integer"}),
                    ("generate_odyssey", {"seed": 42}),
                ]:
                    failed = await client.call_tool(tool, args)
                    assert failed.is_error, (tool, failed)
                # Error responses must not terminate the protocol session.
                assert not (await client.call_tool("project_status")).is_error

    anyio.run(run)
    assert source.read_bytes() == original
