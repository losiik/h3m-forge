"""Local, transport-independent operations for map assistants.

Reads are scoped to the workspace and installed Maps directory. Every mutation
publishes a new bundle under out/mcp; installed maps are reference inputs only.
The format library itself remains independent of MCP and third-party packages.
"""

from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
from threading import Lock
from uuid import uuid4

from h3m import mapfile, paths
from h3m.header import read_header
from h3m.objtypes import Obj
from h3m.stream import BinaryReader
from h3m.world import Assets, WorldSpec, generate_world


MAX_COMPRESSED = 32 * 1024 * 1024
MAX_RAW = 64 * 1024 * 1024


def object_name(kind):
    try:
        return Obj(kind).name
    except ValueError:
        return f"UNKNOWN_{kind}"


def binary_checks(m, raw):
    """Structural checks, deliberately not an editor/playability verdict."""
    issues = []
    templates = m.object_templates or []
    for i, obj in enumerate(m.objects or []):
        if not (0 <= obj.x < m.header.size and 0 <= obj.y < m.header.size
                and 0 <= obj.z < m.header.levels):
            issues.append(f"Object {i}: anchor outside map")
        if not 0 <= obj.template_index < len(templates):
            issues.append(f"Object {i}: invalid template index")
    return dict(full_parse=m.stopped_at is None and not m.tail,
                roundtrip=mapfile.serialize(m) == raw,
                stopped_at=m.stopped_at, opaque_tail_bytes=len(m.tail),
                parsed_fraction=m.parsed_fraction, structural_issues=issues,
                native_editor_verified=False, gameplay_verified=False,
                scope="Binary round-trip and object anchors/templates only; "
                      "does not validate routes, quests, balance or native editor compatibility.")


class MapService:
    def __init__(self, workspace: Path, game_dir: Path | None = None):
        self.workspace = workspace.resolve(strict=True)
        if not self.workspace.is_dir():
            raise ValueError("Workspace must be a directory")
        if game_dir is None:
            try:
                game_dir = paths.find_game_dir()
            except paths.GameNotFoundError:
                pass
        self.game_dir = game_dir.resolve() if game_dir else None
        self.game_maps = (self.game_dir / "Maps").resolve() if self.game_dir else None
        self._generation_lock = Lock()
        self._assets = None

    def status(self):
        return dict(workspace=str(self.workspace), game_dir=str(self.game_dir)
                    if self.game_dir else None,
                    hota_available=bool(self.game_dir and paths.has_hota(self.game_dir)),
                    reference_maps_available=bool(self.game_maps and self.game_maps.is_dir()),
                    output_directory=str(self.workspace / "out" / "mcp"),
                    transport="stdio", target="HotA 1.8.0",
                    operations=["list_maps", "inspect_map", "list_objects", "validate_map",
                                "generate_world", "generate_odyssey", "edit_metadata",
                                "inspect_encounters", "edit_monster"],
                    write_policy="New bundles only; existing and installed maps are preserved.")

    def _input_path(self, value: str):
        candidate = Path(value)
        candidate = (candidate if candidate.is_absolute() else self.workspace / candidate).resolve()
        if not (candidate.is_relative_to(self.workspace)
                or self.game_maps and candidate.is_relative_to(self.game_maps)):
            raise ValueError("Map must be inside the workspace or the installed Maps directory")
        if candidate.suffix.lower() != ".h3m":
            raise ValueError("Only .h3m files are accepted")
        if not candidate.is_file():
            raise ValueError("Map file does not exist")
        return candidate

    def _load(self, value):
        path = self._input_path(value)
        # A bounded snapshot makes the reported hash describe the bytes actually parsed.
        with path.open("rb") as stream:
            packed = stream.read(MAX_COMPRESSED + 1)
        if len(packed) > MAX_COMPRESSED:
            raise ValueError("Compressed map exceeds 32 MiB")
        with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
            raw = stream.read(MAX_RAW + 1)
        if len(raw) > MAX_RAW:
            raise ValueError("Uncompressed map exceeds 64 MiB")
        header = read_header(BinaryReader(raw))
        if not 1 <= header.size <= 252:
            raise ValueError("Map size must be between 1 and 252")
        return path, mapfile.parse(raw), raw, hashlib.sha256(packed).hexdigest()

    @staticmethod
    def _page(items, offset, limit):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("offset must be nonnegative; limit must be 1..200")
        return dict(total=len(items), offset=offset, items=items[offset:offset + limit],
                    next_offset=offset + limit if offset + limit < len(items) else None)

    def list_maps(self, source="generated", offset=0, limit=50):
        if source == "generated":
            root = (self.workspace / "out").resolve()
            if not root.is_relative_to(self.workspace):
                raise ValueError("Output directory leaves workspace")
            files = root.rglob("*.h3m") if root.is_dir() else []
        elif source == "installed":
            files = self.game_maps.glob("*.h3m") if self.game_maps and self.game_maps.is_dir() else []
        else:
            raise ValueError("source must be generated or installed")
        rows = []
        for p in files:
            try:
                p = self._input_path(str(p))
            except ValueError:
                continue
            rows.append(dict(path=str(p), filename=p.name, bytes=p.stat().st_size))
        return self._page(sorted(rows, key=lambda row: row["path"].casefold()), offset, limit)

    def inspect_map(self, path):
        path, m, raw, digest = self._load(path)
        counts = Counter(obj.object_id for obj in m.objects or [])
        return dict(path=str(path), file_sha256=digest, name=m.header.name_text,
                    description=m.header.description_text, format=m.header.format.name,
                    hota_version=m.header.hota.version_string if m.header.hota else None,
                    size=m.header.size, levels=m.header.levels,
                    players=[dict(index=i, human=bool(p.can_human_play),
                                  computer=bool(p.can_computer_play))
                             for i, p in enumerate(m.players) if p.is_playable],
                    objects=sum(counts.values()),
                    object_counts=[dict(id=k, name=object_name(k), count=v)
                                   for k, v in sorted(counts.items())],
                    validation=binary_checks(m, raw))

    def validate_map(self, path):
        path, m, raw, digest = self._load(path)
        return dict(path=str(path), file_sha256=digest, **binary_checks(m, raw))

    def list_objects(self, path, object_id=None, level=None, offset=0, limit=50):
        _, m, _, digest = self._load(path)
        rows = []
        for i, obj in enumerate(m.objects or []):
            if object_id is not None and obj.object_id != object_id:
                continue
            if level is not None and obj.z != level:
                continue
            t = (m.object_templates or [])[obj.template_index]
            rows.append(dict(index=i, object_id=obj.object_id, type=object_name(obj.object_id),
                             subtype=t.object_subid, position=list(obj.position),
                             animation=t.animation_file.decode("ascii", errors="replace"),
                             payload_bytes=len(obj.payload)))
        return dict(file_sha256=digest, full_parse=m.stopped_at is None and not m.tail,
                    **self._page(rows, offset, limit))

    def _output_root(self):
        root = (self.workspace / "out" / "mcp").resolve()
        if not root.is_relative_to(self.workspace):
            raise ValueError("Output directory leaves workspace")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _publish(self, m, report, kind):
        raw = mapfile.serialize(m)
        parsed = mapfile.parse(raw)
        checks = binary_checks(parsed, raw)
        if not checks["full_parse"] or not checks["roundtrip"] or checks["structural_issues"]:
            raise ValueError("Output map failed structural validation")
        root = self._output_root()
        run_id = f"{kind}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:12]}"
        final = root / run_id
        staging = Path(tempfile.mkdtemp(prefix=".building-", dir=root))
        try:
            output = staging / "map.h3m"
            mapfile.save(output, m)
            digest = hashlib.sha256(output.read_bytes()).hexdigest()
            result = dict(report, file_sha256=digest, binary_validation=checks)
            (staging / "report.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            staging.rename(final)
        except BaseException:
            # Only this operation's freshly created temporary directory is removed.
            if staging.resolve().parent == root:
                shutil.rmtree(staging)
            raise
        return dict(run_id=run_id, path=str(final / "map.h3m"),
                    report_path=str(final / "report.json"), file_sha256=digest,
                    report=result)

    def _reference_assets(self):
        if not self.game_dir or not paths.has_hota(self.game_dir):
            raise ValueError("HotA installation is required for generation; set --game-dir")
        if self._assets is None:
            files = [p for p in paths.iter_maps(self.game_dir)
                     if not p.name.startswith("Odyssey-Homecoming")]
            if not files:
                raise ValueError("No reference .h3m maps found in game Maps directory")
            self._assets = Assets.cached(files, self._output_root() / "world-assets.json")
        return self._assets

    def generate_world(self, value):
        spec = WorldSpec.from_dict(value)
        with self._generation_lock:
            world = generate_world(spec, self._reference_assets())
            return self._publish(world.map, dict(world.report, specification=value), "world")

    def generate_odyssey(self, seed=20260905):
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        from odyssey.compact import generate
        with self._generation_lock:
            m, report = generate(self._reference_assets(), seed)
            return self._publish(m, report, "odyssey")

    def edit_metadata(self, path, expected_sha256, name=None, description=None):
        source, m, raw, digest = self._load(path)
        if digest != expected_sha256:
            raise ValueError("Map changed: inspect it again and use the current file_sha256")
        if name is None and description is None:
            raise ValueError("Provide name and/or description")
        if not binary_checks(m, raw)["full_parse"]:
            raise ValueError("Editing requires a fully parsed map")
        if name is not None:
            if not name.strip() or len(name) > 128:
                raise ValueError("name must contain 1..128 characters")
            m.header.name = name.encode("cp1251")
        if description is not None:
            if len(description) > 16384:
                raise ValueError("description exceeds 16384 characters")
            m.header.description = description.encode("cp1251")
        return self._publish(m, dict(operation="edit_metadata", source=str(source),
                                    source_sha256=digest), "edit")

    @staticmethod
    def _require_native_hota(m):
        if not m.header.hota or m.header.hota.level!=9:
            raise ValueError('Semantic encounter tools require native HotA revision 9')

    def inspect_encounters(self, path, offset=0, limit=50):
        from h3m.adventure import read_monster, read_reward
        source,m,raw,digest=self._load(path)
        self._require_native_hota(m)
        rows=[]
        for index,o in enumerate(m.objects or []):
            if o.object_id not in (6,26,54):
                continue
            row=dict(index=index,object_id=o.object_id,position=list(o.position))
            try:
                row['content']=(read_monster(o.payload) if o.object_id==54 else
                                read_reward(o.payload,event=o.object_id==26))
            except (ValueError,EOFError) as error:
                row['unsupported']=str(error)
            if o.object_id==54:
                row['creature']=m.object_templates[o.template_index].object_subid
            rows.append(row)
        return dict(path=str(source),file_sha256=digest,full_parse=not m.tail and m.stopped_at is None,
                    **self._page(rows,offset,limit))

    def edit_monster(self, path, expected_sha256, object_index, count=None, message=None):
        from h3m.adventure import edit_monster, read_monster
        source,m,raw,digest=self._load(path)
        self._require_native_hota(m)
        if digest!=expected_sha256:
            raise ValueError('Map changed: inspect again and use the current file_sha256')
        if not binary_checks(m,raw)['full_parse']:
            raise ValueError('Editing requires a fully parsed map')
        if type(object_index) is not int or not 0<=object_index<len(m.objects):
            raise ValueError('Invalid object index')
        obj=m.objects[object_index]
        if obj.object_id!=54:
            raise ValueError('Selected object is not a monster')
        before=read_monster(obj.payload)
        obj.payload=edit_monster(obj.payload,count=count,message=message)
        return self._publish(m,dict(operation='edit_monster',source=str(source),source_sha256=digest,
            object_index=object_index,before=before,after=read_monster(obj.payload),
            scenario_validation='Not rerun: binary checks do not establish combat balance.'),'edit-monster')
