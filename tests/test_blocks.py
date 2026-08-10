"""Проверки интерпретации блоков на реальных картах.

Главный тест здесь — `test_object_templates_follow_terrain`. Он проверяет не
отдельный блок, а всю цепочку разбора разом: рельеф имеет точно вычислимый
размер, поэтому если сразу за ним лежит правдоподобное число шаблонов
объектов, значит **всё** до него разобрано верно. Ошибись мы на байт в любом
из блоков — от условий победы до предустановленных героев — рельеф съехал бы,
и за ним оказался бы мусор.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from h3m import mapfile, paths
from h3m.terrain import TILE_SIZE, Terrain


def _maps() -> list[Path]:
    try:
        return list(paths.iter_maps())
    except paths.GameNotFoundError:
        return []


ALL_MAPS = _maps()

game_required = pytest.mark.skipif(
    not ALL_MAPS, reason="установка Heroes III не найдена (задайте H3_GAME_DIR)"
)

#: Больше десяти тысяч разных шаблонов объектов на карте не бывает.
MAX_PLAUSIBLE_TEMPLATES = 10_000


@game_required
@pytest.mark.parametrize("map_path", ALL_MAPS, ids=lambda p: p.name)
def test_object_templates_follow_terrain(map_path: Path) -> None:
    """Сразу за рельефом лежит правдоподобное число шаблонов объектов."""
    parsed = mapfile.load(map_path)

    if parsed.terrain is None:
        pytest.skip(f"разбор остановлен: {parsed.stopped_at}")

    assert len(parsed.tail) >= 4
    (template_count,) = struct.unpack_from("<I", parsed.tail, 0)
    assert 0 < template_count < MAX_PLAUSIBLE_TEMPLATES


@game_required
@pytest.mark.parametrize("map_path", ALL_MAPS, ids=lambda p: p.name)
def test_terrain_size_matches_header(map_path: Path) -> None:
    """Размер массива тайлов ровно соответствует объявленному в заголовке."""
    parsed = mapfile.load(map_path)
    if parsed.terrain is None:
        pytest.skip(f"разбор остановлен: {parsed.stopped_at}")

    header = parsed.header
    expected = header.size * header.size * header.levels * TILE_SIZE
    assert len(parsed.terrain.data) == expected


@game_required
def test_terrain_types_are_known() -> None:
    """В рельефе встречаются только существующие типы, и не более 12.

    Если бы массив тайлов начинался не там, первый байт каждой семёрки был бы
    произвольным и почти наверняка вылез бы за диапазон типов рельефа.
    """
    known = {int(terrain) for terrain in Terrain}

    for map_path in ALL_MAPS:
        parsed = mapfile.load(map_path)
        if parsed.terrain is None:
            continue

        used = set(parsed.terrain.terrain_histogram())
        unknown = used - known
        assert not unknown, f"{map_path.name}: неизвестный рельеф {unknown}"


@game_required
def test_main_towns_stand_on_passable_terrain() -> None:
    """Стартовые города не стоят на скалах.

    Смысловая проверка поверх байтовой: координаты города берутся из блока
    игроков, а рельеф — из блока за тысячи байт от него. Если хоть один из
    двух разобран неверно, согласованность между ними сломается.
    """
    for map_path in ALL_MAPS:
        parsed = mapfile.load(map_path)
        if parsed.terrain is None:
            continue

        for index, player in enumerate(parsed.players):
            if not player.has_main_town:
                continue
            x, y, z = player.main_town_pos
            tile = parsed.terrain.tile(x, y, z)
            assert tile.is_passable, (
                f"{map_path.name}: город игрока {index} на скале ({x}, {y}, {z})"
            )


@game_required
def test_rumors_are_plausible() -> None:
    """Слухов немного, и их тексты — непустые строки."""
    for map_path in ALL_MAPS:
        parsed = mapfile.load(map_path)
        if parsed.meta is None:
            continue

        assert len(parsed.meta.rumors) < 100
        for rumor in parsed.meta.rumors:
            assert rumor.text, f"{map_path.name}: пустой слух"
