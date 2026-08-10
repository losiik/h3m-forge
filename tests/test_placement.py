"""Проверки расстановки объектов на сгенерированной карте.

Этим тестам нужна установленная игра: объекты заимствуются из её карт.
"""

from __future__ import annotations

import pytest

from h3m import catalog, generate, mapfile, paths
from h3m.objtypes import TOWN_LIKE, Obj
from h3m.terrain import Terrain

try:
    paths.find_game_dir()
    HAS_GAME = True
except paths.GameNotFoundError:
    HAS_GAME = False

game_required = pytest.mark.skipif(
    not HAS_GAME, reason="установка Heroes III не найдена (задайте H3_GAME_DIR)"
)


def blank() -> mapfile.H3Map:
    return generate.new_map("Тест", size=36, players=2, terrain=Terrain.GRASS)


@game_required
def test_borrowed_decorations_fit_the_terrain() -> None:
    """Заимствованные украшения допустимы на том рельефе, куда их ставят."""
    decorations = catalog.borrow_decorations(limit=5, terrain=Terrain.GRASS)

    assert decorations
    for item in decorations:
        assert item.template.allows_terrain(Terrain.GRASS)
        assert item.payload == b"", "у украшения не должно быть начинки"


@game_required
def test_placed_objects_survive_roundtrip() -> None:
    parsed = blank()
    decorations = catalog.borrow_decorations(limit=3, terrain=Terrain.GRASS)
    for number, (x, y) in enumerate([(5, 5), (7, 9), (12, 3)]):
        catalog.place(parsed, decorations[number], x, y)

    data = mapfile.serialize(parsed)
    again = mapfile.parse(data)

    assert again.objects is not None
    assert len(again.objects) == 3
    assert [(o.x, o.y, o.z) for o in again.objects] == [(5, 5, 0), (7, 9, 0), (12, 3, 0)]
    assert mapfile.serialize(again) == data


@game_required
def test_template_table_has_no_duplicates() -> None:
    """Один шаблон записывается однажды, сколько бы объектов на него ни ссылалось."""
    parsed = blank()
    decoration = catalog.borrow_decorations(limit=1, terrain=Terrain.GRASS)[0]

    for x in range(5, 15):
        catalog.place(parsed, decoration, x, 5)

    assert parsed.object_templates is not None
    assert len(parsed.object_templates) == 1
    assert len(parsed.objects or []) == 10


@game_required
def test_starting_town_offset_matches_real_maps() -> None:
    """Координата города в записи игрока на два тайла левее объекта.

    Смещение (+2, 0) выдержано во всех 182 стартовых городах карт SoD из
    поставки. Совпадение координат, которое кажется естественным, в настоящих
    картах не встречается ни разу.
    """
    parsed = blank()
    generate.place_starting_town(parsed, 0, x=10, y=28)

    player = parsed.players[0]
    assert player.has_main_town == 1
    assert player.main_town_pos == (8, 28, 0)

    towns = [o for o in (parsed.objects or []) if o.object_id in TOWN_LIKE]
    assert len(towns) == 1
    assert (towns[0].x, towns[0].y, towns[0].z) == (10, 28, 0)


@game_required
def test_town_owner_is_written_into_payload() -> None:
    """Владелец города — пятый байт начинки, сразу за идентификатором квестов."""
    parsed = blank()
    generate.place_starting_town(parsed, 1, x=20, y=20)

    towns = [o for o in (parsed.objects or []) if o.object_id in TOWN_LIKE]
    assert towns[0].payload[4] == 1


@game_required
def test_placing_outside_the_map_is_rejected() -> None:
    parsed = blank()
    decoration = catalog.borrow_decorations(limit=1, terrain=Terrain.GRASS)[0]

    with pytest.raises(ValueError, match="вне карты"):
        catalog.place(parsed, decoration, 36, 0)


@game_required
def test_town_for_unplayable_player_is_rejected() -> None:
    parsed = generate.new_map("Тест", players=2)

    with pytest.raises(ValueError, match="не играбелен"):
        generate.place_starting_town(parsed, 5, x=10, y=10)


@game_required
def test_borrowed_town_has_payload() -> None:
    """Город заимствуется вместе с начинкой, а не пустым."""
    town = catalog.borrow(Obj.TOWN, with_payload=True)

    assert town.template.object_id == Obj.TOWN
    assert len(town.payload) > 5
