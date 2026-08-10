"""Проверки обнаружения установленной игры.

Тесты, которым нужна установленная игра, помечены и пропускаются, если её нет:
проект должен собираться и на машине без Heroes III.
"""

from __future__ import annotations

import pytest

from h3m import paths


def _has_game() -> bool:
    try:
        paths.find_game_dir()
    except paths.GameNotFoundError:
        return False
    return True


game_required = pytest.mark.skipif(
    not _has_game(),
    reason="установка Heroes III не найдена (задайте H3_GAME_DIR)",
)


@game_required
def test_game_dir_found():
    assert paths.find_game_dir().is_dir()


@game_required
def test_maps_dir_has_maps():
    maps = list(paths.iter_maps())
    assert maps, "в каталоге Maps не найдено ни одного .h3m"


@game_required
def test_maps_sorted_by_size():
    sizes = [p.stat().st_size for p in paths.iter_maps()]
    assert sizes == sorted(sizes)
