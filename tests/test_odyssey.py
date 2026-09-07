"""Проверки карты «Одиссея».

Тесты делятся надвое: согласованность дизайна проверяется без игры, а сборка
карты требует установленной поставки — объекты заимствуются из её карт.
"""

from __future__ import annotations

import pytest

from h3m import mapfile, passability, paths
from h3m.objtypes import MONSTER_LIKE, SIGN_LIKE, TOWN_LIKE, Obj
from h3m.stream import decode
from odyssey import build, design

FILE_TRAILING = 124

try:
    paths.find_game_dir()
    HAS_GAME = True
except paths.GameNotFoundError:
    HAS_GAME = False

game_required = pytest.mark.skipif(
    not HAS_GAME, reason="установка Heroes III не найдена (задайте H3_GAME_DIR)"
)


# --- дизайн: игре не нужен -----------------------------------------------


def test_design_is_consistent() -> None:
    assert design.validate() == []


def test_every_episode_has_text() -> None:
    """У каждого эпизода есть замысел и текст таблички — иначе он пустой."""
    for episode in design.ROUTE:
        assert episode.idea.strip(), f"{episode.key}: не описан замысел"
        assert episode.sign.strip(), f"{episode.key}: нет текста таблички"


def test_ambushes_follow_their_cause() -> None:
    """Гнев Посейдона не может начаться раньше ослепления Полифема."""
    keys = [episode.key for episode in design.ROUTE]
    cause = keys.index("polyphemus")

    for ambush in design.POSEIDON_AMBUSHES:
        for neighbour in ambush.between:
            assert keys.index(neighbour) >= cause


def test_guards_cover_the_battles() -> None:
    """У каждого эпизода-боя есть охрана, иначе бой не состоится."""
    for episode in design.ROUTE:
        if episode.kind is design.Kind.BATTLE:
            assert build.GUARDS.get(episode.key), f"{episode.key}: бой без охраны"


# --- сборка: нужна поставка ----------------------------------------------


@game_required
def test_map_parses_to_the_very_end() -> None:
    data = mapfile.serialize(build.build_map())
    parsed = mapfile.parse(data)

    assert parsed.stopped_at is None
    assert parsed.tail == b""
    assert parsed.events is not None
    assert len(parsed.events.trailing) == FILE_TRAILING


@game_required
def test_map_roundtrips() -> None:
    data = mapfile.serialize(build.build_map())
    assert mapfile.serialize(mapfile.parse(data)) == data


@game_required
def test_build_is_deterministic() -> None:
    """Одна и та же карта собирается байт в байт при каждом запуске."""
    assert mapfile.serialize(build.build_map()) == mapfile.serialize(build.build_map())


@game_required
def test_objects_land_inside_the_map() -> None:
    parsed = build.build_map()
    size, levels = parsed.header.size, parsed.header.levels

    for instance in parsed.objects or []:
        assert 0 <= instance.x < size
        assert 0 <= instance.y < size
        assert instance.z < levels


@game_required
def test_no_two_objects_share_a_tile() -> None:
    """Объекты не стоят друг на друге.

    Верхний объект просто скрывает нижний, и карта молча теряет содержимое.
    Ни round-trip, ни разбор такого не замечают — файл-то корректен, — поэтому
    на первой сборке три таблички пропали под отрядом, ящиком и другой
    табличкой, и заметил это только человек в редакторе.
    """
    parsed = build.build_map()
    spots = [(i.x, i.y, i.z) for i in (parsed.objects or [])]

    duplicates = {spot for spot in spots if spots.count(spot) > 1}
    assert not duplicates, f"на одной клетке несколько объектов: {sorted(duplicates)}"


@game_required
def test_underground_holds_the_hades_episode() -> None:
    """В подземелье лежит ровно эпизод Аида и ничего лишнего."""
    parsed = build.build_map()
    below = [i for i in (parsed.objects or []) if i.z == 1]

    assert below, "подземелье пусто"
    assert any(i.object_id == Obj.SEER_HUT for i in below), "нет хижины провидца"
    assert any(i.object_id in MONSTER_LIKE for i in below), "нет охраны"


@game_required
def test_guard_is_the_only_way_into_ithaca() -> None:
    """Стена вокруг Итаки делает стража настоящим препятствием.

    Проверка смысла, а не формата: барьер, который обходится по траве, —
    совершенно корректные данные и бессмысленная карта. Ни round-trip, ни
    разбор такого не заметят.
    """
    parsed = build.build_map()
    blocked = passability.blocked_tiles(parsed)

    troy = design.episode("troy").anchor
    ithaca = build.ithaca_town_position()
    guard = next(i for i in parsed.objects if i.object_id == Obj.QUEST_GUARD)
    gate = (guard.x, guard.y, guard.z)

    assert passability.can_approach(parsed, troy, gate, blocked=blocked), (
        "до стража нельзя дойти — он заперт собственной стеной"
    )
    assert passability.can_approach(parsed, troy, ithaca, blocked=blocked - {gate}), (
        "через стража Итака недостижима — проход перекрыт"
    )
    assert not passability.can_approach(
        parsed, troy, ithaca, blocked=blocked | {gate}
    ), "Итаку можно обойти мимо стража — стена дырявая"


@game_required
def test_every_episode_is_reachable() -> None:
    """К каждому эпизоду и каждой засаде можно подойти от Трои."""
    parsed = build.build_map()
    guard = next(i for i in parsed.objects if i.object_id == Obj.QUEST_GUARD)
    passable = passability.blocked_tiles(parsed) - {(guard.x, guard.y, guard.z)}
    troy = design.episode("troy").anchor

    for episode in design.ROUTE:
        if episode.anchor[2] != troy[2]:
            continue
        # У финала опора эпизода тонет под городом, поэтому целимся в город.
        target = (
            build.ithaca_town_position()
            if episode.kind is design.Kind.FINALE
            else episode.anchor
        )
        assert passability.can_approach(
            parsed, troy, target, blocked=passable
        ), f"{episode.key}: до эпизода не добраться"

    for ambush in design.POSEIDON_AMBUSHES:
        assert passability.can_approach(
            parsed, troy, ambush.position, blocked=passable
        ), f"{ambush.key}: до засады не добраться"


@game_required
def test_signs_carry_the_designed_texts() -> None:
    """Тексты из дизайна доезжают до карты и читаются обратно."""
    parsed = build.build_map()
    on_map = {
        decode(instance.payload[4 : 4 + int.from_bytes(instance.payload[:4], "little")])
        for instance in (parsed.objects or [])
        if instance.object_id in SIGN_LIKE
    }

    for episode in design.ROUTE:
        assert episode.sign in on_map, f"{episode.key}: текст не попал на карту"


@game_required
def test_start_and_finale_have_towns() -> None:
    parsed = build.build_map()
    towns = [i for i in (parsed.objects or []) if i.object_id in TOWN_LIKE]
    assert len(towns) == 2

    positions = {(t.x, t.y, t.z) for t in towns}
    assert build.troy_town_position() in positions
    assert build.ithaca_town_position() in positions


@game_required
def test_victory_is_capturing_ithaca() -> None:
    parsed = build.build_map()
    assert parsed.victory is not None

    x, y, z = build.ithaca_town_position()
    assert parsed.victory.payload == bytes([x, y, z]), (
        "условие победы должно указывать на сам город, а не на опору эпизода"
    )
    assert parsed.victory.allow_normal_victory == 0, (
        "обычная победа при отсутствии противников сработала бы в первый день"
    )


@game_required
def test_guards_gate_the_route() -> None:
    """Охрана эпизода перекрывает путь ко всем последующим.

    Главная проверка замысла. Странствие должно идти по порядку: не одолев
    циклопа, к сиренам не попасть. Держится это на географии — острова связаны
    перешейками в одну клетку, и охрана стоит в горловинах.

    Проверять расстояние от охраны до эпизода бессмысленно: важно не где она
    стоит, а что она запирает.
    """
    parsed = build.build_map()
    passable = passability.blocked_tiles(parsed)
    troy = design.episode("troy").anchor
    surface = [e for e in design.ROUTE if e.anchor[2] == troy[2]]

    def target(episode):
        return (
            build.ithaca_town_position()
            if episode.kind is design.Kind.FINALE
            else episode.anchor
        )

    for index, episode in enumerate(surface):
        later = surface[index + 1 :]
        if not build.GUARDS.get(episode.key) or not later:
            continue

        guards = {
            (i.x, i.y, i.z)
            for i in (parsed.objects or [])
            if i.object_id in MONSTER_LIKE
            and abs(i.x - episode.anchor[0]) <= 8
            and abs(i.y - episode.anchor[1]) <= 8
        }
        if not guards:
            continue

        blocked = passable | guards
        reachable_later = [
            e.title
            for e in later
            if passability.can_approach(parsed, troy, target(e), blocked=blocked)
        ]
        # Последний перед Итакой заперт стражем квеста, а не боем.
        if episode.key == "helios":
            continue
        assert not reachable_later, (
            f"{episode.key}: минуя охрану, доступны {reachable_later}"
        )
