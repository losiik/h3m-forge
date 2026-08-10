"""Настройки восьми игроков.

Блок неприятен тем, что запись игрока имеет переменную длину и переменный
состав: за игрока, за которого нельзя играть, хранится короткий огрызок; поля
стартового города и стартового героя появляются только при соответствующих
флагах; ширина маски фракций зависит от версии формата.

Всё, что не разобрано на поля (выравнивание, назначение чего мы пока не знаем),
сохраняется сырыми байтами и пишется обратно как есть. Это позволяет добиться
побайтового round-trip, не понимая формат до последнего бита, — и разбираться
с непонятыми полями постепенно, а не блокировать на них всю работу.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from h3m.format import MapFeatures
from h3m.stream import BinaryReader, BinaryWriter, decode

log = logging.getLogger(__name__)

PLAYER_COUNT = 8

#: Значение поля «стартовый герой», означающее «героя нет».
NO_HERO = 0xFF


@dataclass(slots=True)
class CustomHero:
    """Именованный герой, доступный игроку (AB и старше)."""

    hero_id: int
    name: bytes

    @property
    def name_text(self) -> str:
        return decode(self.name)


@dataclass(slots=True)
class PlayerInfo:
    """Настройки одного игрока."""

    can_human_play: int
    can_computer_play: int

    #: Сырые байты усечённой записи — заполняется, только если играть нельзя.
    unplayable_padding: bytes = b""

    ai_tactic: int = 0
    sod_faction_flag: bytes = b""
    """Байт, появившийся в SoD. Назначение точно не установлено, пишем как есть."""

    allowed_factions: int = 0
    is_faction_random: int = 0

    has_main_town: int = 0
    generate_hero_at_main_town: int = 0
    main_town_type: int = 0
    main_town_pos: tuple[int, int, int] = (0, 0, 0)

    has_random_hero: int = 0
    main_custom_hero_id: int = NO_HERO
    main_custom_hero_portrait: int = 0
    main_custom_hero_name: bytes = b""

    ab_padding: bytes = b""
    custom_heroes: list[CustomHero] = field(default_factory=list)

    @property
    def is_playable(self) -> bool:
        return bool(self.can_human_play or self.can_computer_play)

    def __str__(self) -> str:
        if not self.is_playable:
            return "—"
        who = []
        if self.can_human_play:
            who.append("человек")
        if self.can_computer_play:
            who.append("ИИ")
        parts = ["/".join(who)]
        if self.has_main_town:
            x, y, z = self.main_town_pos
            parts.append(f"город ({x},{y},{z})")
        if self.main_custom_hero_id != NO_HERO:
            parts.append(f"герой #{self.main_custom_hero_id}")
        return ", ".join(parts)


def read_players(reader: BinaryReader, features: MapFeatures) -> list[PlayerInfo]:
    """Прочитать записи всех восьми игроков."""
    return [_read_player(reader, features, index) for index in range(PLAYER_COUNT)]


def _read_player(reader: BinaryReader, features: MapFeatures, index: int) -> PlayerInfo:
    can_human = reader.u8()
    can_computer = reader.u8()

    player = PlayerInfo(can_human_play=can_human, can_computer_play=can_computer)

    if not player.is_playable:
        player.unplayable_padding = reader.bytes_(features.unplayable_player_padding)
        log.debug("Игрок %d: не играбелен, огрызок %d байт", index,
                  len(player.unplayable_padding))
        return player

    player.ai_tactic = reader.i8()

    if features.is_sod_or_later:
        player.sod_faction_flag = reader.bytes_(1)

    player.allowed_factions = int.from_bytes(
        reader.bytes_(features.faction_mask_bytes), "little"
    )
    player.is_faction_random = reader.u8()
    player.has_main_town = reader.u8()

    if player.has_main_town:
        if features.is_ab_or_later:
            player.generate_hero_at_main_town = reader.u8()
            player.main_town_type = reader.u8()
        player.main_town_pos = (reader.u8(), reader.u8(), reader.u8())

    player.has_random_hero = reader.u8()
    player.main_custom_hero_id = reader.u8()

    if player.main_custom_hero_id != NO_HERO:
        player.main_custom_hero_portrait = reader.u8()
        player.main_custom_hero_name = reader.string()

    if features.is_ab_or_later:
        player.ab_padding = reader.bytes_(1)
        hero_count = reader.u32()
        player.custom_heroes = [
            CustomHero(hero_id=reader.u8(), name=reader.string())
            for _ in range(hero_count)
        ]

    log.debug("Игрок %d: %s", index, player)
    return player


def write_players(
    writer: BinaryWriter, players: list[PlayerInfo], features: MapFeatures
) -> None:
    """Записать записи игроков обратно. Зеркало read_players."""
    for player in players:
        _write_player(writer, player, features)


def _write_player(
    writer: BinaryWriter, player: PlayerInfo, features: MapFeatures
) -> None:
    writer.u8(player.can_human_play)
    writer.u8(player.can_computer_play)

    if not player.is_playable:
        writer.bytes_(player.unplayable_padding)
        return

    writer.i8(player.ai_tactic)

    if features.is_sod_or_later:
        writer.bytes_(player.sod_faction_flag)

    writer.bytes_(
        player.allowed_factions.to_bytes(features.faction_mask_bytes, "little")
    )
    writer.u8(player.is_faction_random)
    writer.u8(player.has_main_town)

    if player.has_main_town:
        if features.is_ab_or_later:
            writer.u8(player.generate_hero_at_main_town)
            writer.u8(player.main_town_type)
        for coordinate in player.main_town_pos:
            writer.u8(coordinate)

    writer.u8(player.has_random_hero)
    writer.u8(player.main_custom_hero_id)

    if player.main_custom_hero_id != NO_HERO:
        writer.u8(player.main_custom_hero_portrait)
        writer.string(player.main_custom_hero_name)

    if features.is_ab_or_later:
        writer.bytes_(player.ab_padding)
        writer.u32(len(player.custom_heroes))
        for hero in player.custom_heroes:
            writer.u8(hero.hero_id)
            writer.string(hero.name)
