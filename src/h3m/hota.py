"""Creation profile for HotA 1.8.0 (H3M revision 9).

Defaults measured from editor-created probe_town.h3m / probe_1monster.h3m.
Only the empty/default forms are supported; this is not a general script writer.
No game sprites or complete source maps are embedded here.
"""

from h3m import generate, options
from h3m.format import MapFormat, features_for
from h3m.header import HotaHeader
from h3m.heroes import PredefinedHeroes


def new_map(name: str, description: str = "", **kwargs):
    """Create native HotA, retaining the existing SoD generator API."""
    result = generate.new_map(name, description, **kwargs)
    features = features_for(MapFormat.HOTA, 9)
    result.header.format = MapFormat.HOTA
    result.header.features = features
    result.header.hota = HotaHeader(
        level=9, version_major=1, version_minor=8, version_patch=0,
        terrain_types_count=12, town_types_count=12, allowed_difficulties_mask=31,
    )
    for player in result.playable_players:
        player.allowed_factions = (1 << features.factions) - 1
    meta = result.meta
    meta.allowed_heroes = options.SizedMask(
        bytes.fromhex("ffffefffffffffff7fffffffffffffffffff0070ff4ffeffc7ff7f"), 215
    )
    meta.allowed_artifacts = options.SizedMask(
        bytes.fromhex("000000000000000e00000800000000c0ffff000023"), 166
    )
    meta.allowed_skills = bytes.fromhex("00000004")
    meta.options.hota_special_months = bytes.fromhex("01000000")
    meta.options.combined_artifacts_count = 16
    meta.options.combined_artifacts_mask = bytes.fromhex("0200")
    meta.options.round_limit = -1
    meta.options.recruitment_flags = bytes(8)
    meta.hota_scripts_flag = b"\x00"
    result.predefined_heroes = PredefinedHeroes(
        declared_count=215, hota_extra=bytes.fromhex("010001000000") * 215
    )
    return result


def town_payload(identifier: int, owner: int) -> bytes:
    """Default town with fort, no custom garrison, buildings, name or events.

    Keep the editor's default extension opaque until its fields are known.
    Unlike copying a scenario town, this carries no unrelated event or army.
    """
    if owner not in (*range(8), 255):
        raise ValueError("invalid town owner")
    data = bytearray(89)
    data[:4] = identifier.to_bytes(4, "little")
    data[4] = owner
    data[9] = 1
    data[28:30] = b"\x01\x30"
    data[85] = 255
    return bytes(data)
