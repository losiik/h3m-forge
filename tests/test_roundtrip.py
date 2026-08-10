"""Основные проверки на реальных картах из поставки.

Здесь два разных вида проверок, и они ловят разные ошибки:

* **round-trip** — что разобранное собирается обратно байт в байт. Ловит
  регрессии в уже понятой части формата, но не ловит неверную интерпретацию:
  нераспознанный хвост пишется как есть, так что ошибись мы в разбиении на
  поля — сборка всё равно совпадёт;
* **правдоподобие следующего поля** — что разбор кончается там, где мы думаем.
  Вот это и ловит неверную интерпретацию.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from h3m import mapfile, paths
from h3m.container import read_map_bytes
from h3m.header import read_header
from h3m.players import PLAYER_COUNT, read_players
from h3m.stream import BinaryReader


def _maps() -> list[Path]:
    try:
        return list(paths.iter_maps())
    except paths.GameNotFoundError:
        return []


ALL_MAPS = _maps()

game_required = pytest.mark.skipif(
    not ALL_MAPS, reason="установка Heroes III не найдена (задайте H3_GAME_DIR)"
)

#: Известные коды условия победы: 0..12 либо «стандартное» 0xFF.
VALID_VICTORY_CODES = set(range(13)) | {0xFF}


@game_required
@pytest.mark.parametrize("map_path", ALL_MAPS, ids=lambda p: p.name)
def test_roundtrip_is_byte_exact(map_path: Path) -> None:
    """Карта собирается обратно байт в байт."""
    data = read_map_bytes(map_path)
    assert mapfile.serialize(mapfile.parse(data)) == data


@game_required
@pytest.mark.parametrize("map_path", ALL_MAPS, ids=lambda p: p.name)
def test_players_end_where_expected(map_path: Path) -> None:
    """Сразу за блоком игроков лежит правдоподобный код условия победы.

    Независимая проверка интерпретации: если разбор игроков уехал хотя бы на
    байт, здесь окажется произвольное значение. Именно так была поймана ошибка
    с накопительными пропусками в огрызке неиграбельного игрока.
    """
    reader = BinaryReader(read_map_bytes(map_path))
    header = read_header(reader)
    players = read_players(reader, header.features)

    assert len(players) == PLAYER_COUNT
    assert reader.u8() in VALID_VICTORY_CODES


@game_required
def test_every_map_has_at_least_one_playable_player() -> None:
    """Карта без играбельных игроков бессмысленна — значит, разбор соврал."""
    for map_path in ALL_MAPS:
        parsed = mapfile.load(map_path)
        assert parsed.playable_players, f"{map_path.name}: ни одного игрока"


@game_required
def test_main_town_positions_are_inside_map() -> None:
    """Стартовые города лежат в границах карты.

    Координаты читаются тремя байтами подряд, и если блок игроков смещён,
    сюда попадёт мусор, почти наверняка выходящий за границы.
    """
    for map_path in ALL_MAPS:
        parsed = mapfile.load(map_path)
        size = parsed.header.size
        levels = parsed.header.levels

        for index, player in enumerate(parsed.players):
            if not player.has_main_town:
                continue
            x, y, z = player.main_town_pos
            assert 0 <= x < size, f"{map_path.name}: игрок {index}, x={x}"
            assert 0 <= y < size, f"{map_path.name}: игрок {index}, y={y}"
            assert z < levels, f"{map_path.name}: игрок {index}, z={z}"
