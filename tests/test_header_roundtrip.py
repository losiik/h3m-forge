"""Round-trip заголовка на реальных картах из поставки.

Тест намеренно построен на данных игры, а не на подготовленных фикстурах:
фикстуру я сочиню под своё же понимание формата и ошибку в нём не поймаю.
Реальные файлы такого снисхождения не проявляют.

Карты в репозиторий не входят, поэтому без установленной игры тест
пропускается.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from h3m import paths
from h3m.container import read_map_bytes
from h3m.format import MapFormat
from h3m.header import read_header, write_header
from h3m.stream import BinaryReader, BinaryWriter


def _maps() -> list[Path]:
    try:
        return list(paths.iter_maps())
    except paths.GameNotFoundError:
        return []


ALL_MAPS = _maps()

game_required = pytest.mark.skipif(
    not ALL_MAPS, reason="установка Heroes III не найдена (задайте H3_GAME_DIR)"
)


@game_required
@pytest.mark.parametrize("map_path", ALL_MAPS, ids=lambda p: p.name)
def test_header_roundtrip(map_path: Path) -> None:
    """Заголовок собирается обратно байт в байт."""
    data = read_map_bytes(map_path)

    reader = BinaryReader(data)
    header = read_header(reader)
    header_length = reader.pos

    writer = BinaryWriter()
    write_header(writer, header)

    assert writer.getvalue() == data[:header_length]


@game_required
def test_all_formats_present() -> None:
    """В поставке есть карты всех четырёх версий — иначе проверка неполна."""
    found = set()
    for map_path in ALL_MAPS:
        reader = BinaryReader(read_map_bytes(map_path))
        found.add(read_header(reader).format)

    assert {MapFormat.ROE, MapFormat.AB, MapFormat.SOD, MapFormat.HOTA} <= found


@game_required
def test_hota_header_is_plausible() -> None:
    """HotA-поля заголовка осмысленны, а не случайный мусор.

    Если бы блок HotA-полей был разобран неверно, эти значения поехали бы
    первыми: размер карты обязан быть одним из допустимых, а число типов
    террейна у HotA — ровно 12 (10 базовых плюс Highlands и Wasteland).
    """
    valid_sizes = {36, 72, 108, 144, 180, 216, 252}
    checked = 0

    for map_path in ALL_MAPS:
        reader = BinaryReader(read_map_bytes(map_path))
        header = read_header(reader)
        if header.format is not MapFormat.HOTA:
            continue

        checked += 1
        assert header.hota is not None
        assert header.size in valid_sizes
        assert header.hota.terrain_types_count == 12
        assert 0 <= header.hota.allowed_difficulties_mask <= 31
        assert header.hota.version_major >= 1

    assert checked, "HotA-карт не нашлось"
