import gzip
from pathlib import Path

import pytest

from h3m import hota, mapfile
from h3m.service import MapService


@pytest.fixture
def service(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return MapService(workspace, tmp_path / "no-game")


@pytest.fixture
def source(service):
    path = service.workspace / "source.h3m"
    mapfile.save(path, hota.new_map("Исходная карта", size=72, players=2))
    return path


def test_inspection_and_metadata_copy_preserve_source(service, source):
    original = source.read_bytes()
    inspected = service.inspect_map(str(source))
    assert inspected["name"] == "Исходная карта"
    assert inspected["validation"]["full_parse"]
    assert inspected["validation"]["roundtrip"]
    assert not inspected["validation"]["native_editor_verified"]
    result = service.edit_metadata(str(source), inspected["file_sha256"],
                                   name="Новое имя", description="Описание для игрока")
    assert source.read_bytes() == original
    copied = mapfile.load(Path(result["path"]))
    assert copied.header.name_text == "Новое имя"
    assert copied.header.description_text == "Описание для игрока"
    copied.header.name = "Исходная карта".encode("cp1251")
    copied.header.description = mapfile.load(source).header.description
    assert mapfile.serialize(copied) == gzip.decompress(original)
    assert Path(result["report_path"]).is_file()
    assert service.validate_map(result["path"])["file_sha256"] == result["file_sha256"]
    second = service.edit_metadata(str(source), inspected["file_sha256"], name="Другая копия")
    assert second["path"] != result["path"]
    assert service.list_maps(limit=1)["total"] == 2
    assert service.list_maps(limit=1)["next_offset"] == 1


def test_stale_hash_and_bad_text_do_not_write(service, source):
    with pytest.raises(ValueError, match="Map changed"):
        service.edit_metadata(str(source), "0" * 64, name="Изменение")
    digest = service.inspect_map(str(source))["file_sha256"]
    with pytest.raises(UnicodeEncodeError):
        service.edit_metadata(str(source), digest, name="🏝")
    assert not (service.workspace / "out").exists()


def test_paths_are_scoped_and_symlinks_resolved(service, tmp_path):
    outside = tmp_path / "outside.h3m"
    mapfile.save(outside, hota.new_map("Outside"))
    for path in (str(outside), "../outside.h3m", "../workspace2/outside.h3m"):
        with pytest.raises(ValueError, match="inside the workspace"):
            service.inspect_map(path)
    with pytest.raises(ValueError, match="Only .h3m"):
        service.inspect_map("pyproject.toml")


def test_symlink_escape(service, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (service.workspace / "out").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires Windows developer mode or privilege")
    with pytest.raises(ValueError, match="leaves workspace"):
        service._output_root()


def test_partial_parse_is_not_editable(service, source):
    with gzip.open(source, "ab") as stream:
        stream.write(b"opaque")
    info = service.inspect_map(str(source))
    assert not info["validation"]["full_parse"]
    # The parser rolls back the entire events block when trailing bytes are found.
    assert info["validation"]["opaque_tail_bytes"] >= 6
    assert info["validation"]["roundtrip"]
    with pytest.raises(ValueError, match="fully parsed"):
        service.edit_metadata(str(source), info["file_sha256"], name="New")


def test_bounded_decompression(service, source, monkeypatch):
    monkeypatch.setattr("h3m.service.MAX_RAW", 20)
    with pytest.raises(ValueError, match="Uncompressed map exceeds"):
        service.inspect_map(str(source))


def test_bad_gzip_and_invalid_pagination(service):
    bad = service.workspace / "broken.h3m"
    bad.write_bytes(b"not a gzip file")
    with pytest.raises(gzip.BadGzipFile):
        service.validate_map(str(bad))
    with pytest.raises(ValueError, match="limit"):
        service.list_maps(limit=1000000)


def test_invalid_generation_spec_fails_before_assets(service):
    with pytest.raises(ValueError, match="connected"):
        service.generate_world(dict(name="Invalid", zones=[dict(id="a", player=0),
                                                           dict(id="b", player=1)],
                                    connections=[]))
    assert not (service.workspace / "out").exists()
    with pytest.raises(ValueError, match="HotA installation"):
        service.generate_odyssey()


def test_failed_publication_leaves_no_bundle(service, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("simulated disk failure")
    monkeypatch.setattr(mapfile, "save", fail)
    with pytest.raises(OSError, match="simulated"):
        service._publish(hota.new_map("Test"), {}, "test")
    assert list((service.workspace / "out/mcp").iterdir()) == []
