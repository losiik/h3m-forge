"""Блоки между условиями победы и рельефом.

Команды, разрешённые герои, выбывшие герои, настройки карты, разрешённые
артефакты, заклинания и навыки, слухи.

Битовые маски хранятся сырыми байтами вместе с объявленной длиной. У HotA
маски «размерные»: сначала четырёхбайтовое число сущностей, затем маска
рассчитанной под него длины. Хранить объявленное число обязательно — вычислять
его заново при записи нельзя, иначе карта, где оно отличается от ожидаемого,
не соберётся обратно.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from h3m.format import MapFeatures
from h3m.stream import BinaryReader, BinaryWriter, decode

log = logging.getLogger(__name__)

PLAYER_COUNT = 8

#: Блок нулей между настройками героев и опциями карты.
RESERVED_ZEROS = 31


class UnsupportedBlockError(NotImplementedError):
    """Блок встретился во включённом состоянии, а разбирать его мы ещё не умеем.

    Не ошибка, а честная остановка: всё, начиная с этого блока, останется
    сырым хвостом, и round-trip от этого не пострадает.
    """


@dataclass(slots=True)
class SizedMask:
    """Битовая маска: либо фиксированной длины, либо с объявленным размером."""

    data: bytes
    declared_count: int | None = None
    """Число сущностей, записанное перед маской. Есть только у HotA."""

    @property
    def allowed(self) -> int:
        """Сколько бит установлено — для показа человеку."""
        return sum(byte.bit_count() for byte in self.data)


@dataclass(slots=True)
class TeamInfo:
    """Разбиение игроков по командам."""

    count: int
    assignments: bytes = b""
    """По байту на игрока. Пусто, если команд нет."""


@dataclass(slots=True)
class DisposedHero:
    """Герой, недоступный для найма частью игроков."""

    hero_id: int
    portrait: int
    name: bytes
    players_mask: int

    @property
    def name_text(self) -> str:
        return decode(self.name)


@dataclass(slots=True)
class MapOptions:
    """Настройки карты, лежащие после блока героев."""

    reserved: bytes = b""
    hota_special_months: bytes = b""
    combined_artifacts_count: int | None = None
    combined_artifacts_mask: bytes = b""
    round_limit: int | None = None
    recruitment_flags: bytes = b""


@dataclass(slots=True)
class Rumor:
    """Слух, показываемый в таверне."""

    name: bytes
    text: bytes

    @property
    def name_text(self) -> str:
        return decode(self.name)

    @property
    def text_text(self) -> str:
        return decode(self.text)


@dataclass(slots=True)
class MapMeta:
    """Всё, что лежит между условиями победы и предустановленными героями."""

    teams: TeamInfo
    allowed_heroes: SizedMask
    hero_placeholders: list[int] = field(default_factory=list)
    disposed_heroes: list[DisposedHero] = field(default_factory=list)
    options: MapOptions = field(default_factory=MapOptions)
    hota_scripts_flag: bytes = b""
    allowed_artifacts: SizedMask | None = None
    allowed_spells: bytes = b""
    allowed_skills: bytes = b""
    rumors: list[Rumor] = field(default_factory=list)


# --- команды ------------------------------------------------------------


def read_teams(reader: BinaryReader) -> TeamInfo:
    count = reader.u8()
    assignments = reader.bytes_(PLAYER_COUNT) if count > 0 else b""
    return TeamInfo(count=count, assignments=assignments)


def write_teams(writer: BinaryWriter, teams: TeamInfo) -> None:
    writer.u8(teams.count)
    if teams.count > 0:
        writer.bytes_(teams.assignments)


# --- герои --------------------------------------------------------------


def read_allowed_heroes(
    reader: BinaryReader, features: MapFeatures
) -> tuple[SizedMask, list[int]]:
    if features.is_hota:
        declared = reader.u32()
        mask = SizedMask(reader.bytes_((declared + 7) // 8), declared_count=declared)
    else:
        mask = SizedMask(reader.bytes_(features.heroes_bytes))

    placeholders: list[int] = []
    if features.is_ab_or_later:
        placeholders = [reader.u8() for _ in range(reader.u32())]

    log.debug("Разрешено героев: %d, заглушек кампании: %d",
              mask.allowed, len(placeholders))
    return mask, placeholders


def write_allowed_heroes(
    writer: BinaryWriter,
    mask: SizedMask,
    placeholders: list[int],
    features: MapFeatures,
) -> None:
    if features.is_hota:
        writer.u32(mask.declared_count or 0)
    writer.bytes_(mask.data)

    if features.is_ab_or_later:
        writer.u32(len(placeholders))
        for hero_id in placeholders:
            writer.u8(hero_id)


def read_disposed_heroes(
    reader: BinaryReader, features: MapFeatures
) -> list[DisposedHero]:
    if not features.is_sod_or_later:
        return []

    return [
        DisposedHero(
            hero_id=reader.u8(),
            portrait=reader.u8(),
            name=reader.string(),
            players_mask=reader.u8(),
        )
        for _ in range(reader.u8())
    ]


def write_disposed_heroes(
    writer: BinaryWriter, heroes: list[DisposedHero], features: MapFeatures
) -> None:
    if not features.is_sod_or_later:
        return

    writer.u8(len(heroes))
    for hero in heroes:
        writer.u8(hero.hero_id)
        writer.u8(hero.portrait)
        writer.string(hero.name)
        writer.u8(hero.players_mask)


# --- настройки карты ----------------------------------------------------


def read_map_options(reader: BinaryReader, features: MapFeatures) -> MapOptions:
    options = MapOptions(reserved=reader.bytes_(RESERVED_ZEROS))

    if features.is_hota:
        # флаг случайных особых месяцев плюс три нулевых байта
        options.hota_special_months = reader.bytes_(4)

    if features.hota_has_combined_artifacts:
        count = reader.i32()
        options.combined_artifacts_count = count
        options.combined_artifacts_mask = reader.bytes_((count + 7) // 8)

    if features.hota_has_round_limit:
        options.round_limit = reader.i32()

    if features.hota_has_recruitment_flags:
        options.recruitment_flags = reader.bytes_(PLAYER_COUNT)

    return options


def write_map_options(
    writer: BinaryWriter, options: MapOptions, features: MapFeatures
) -> None:
    writer.bytes_(options.reserved)

    if features.is_hota:
        writer.bytes_(options.hota_special_months)

    if features.hota_has_combined_artifacts:
        writer.i32(options.combined_artifacts_count or 0)
        writer.bytes_(options.combined_artifacts_mask)

    if features.hota_has_round_limit:
        writer.i32(options.round_limit or 0)

    if features.hota_has_recruitment_flags:
        writer.bytes_(options.recruitment_flags)


def read_hota_scripts(reader: BinaryReader, features: MapFeatures) -> bytes:
    """Собственная система событий HotA.

    Пока умеем только выключенное состояние — это один байт-флаг. Если система
    включена, честно останавливаемся: дальше идут списки событий с вложенными
    действиями, и угадывать их структуру смысла нет.
    """
    if not features.hota_has_scripts:
        return b""

    flag = reader.bytes_(1)
    if flag[0]:
        raise UnsupportedBlockError(
            "включена система событий HotA — разбор этого блока не реализован"
        )
    return flag


def write_hota_scripts(writer: BinaryWriter, flag: bytes) -> None:
    writer.bytes_(flag)


# --- разрешённое --------------------------------------------------------


def read_allowed_artifacts(
    reader: BinaryReader, features: MapFeatures
) -> SizedMask | None:
    if not features.is_ab_or_later:
        return None

    if features.is_hota:
        declared = reader.u32()
        return SizedMask(reader.bytes_((declared + 7) // 8), declared_count=declared)

    return SizedMask(reader.bytes_(features.artifacts_bytes))


def write_allowed_artifacts(
    writer: BinaryWriter, mask: SizedMask | None, features: MapFeatures
) -> None:
    if not features.is_ab_or_later or mask is None:
        return

    if features.is_hota:
        writer.u32(mask.declared_count or 0)
    writer.bytes_(mask.data)


def read_allowed_spells_skills(
    reader: BinaryReader, features: MapFeatures
) -> tuple[bytes, bytes]:
    if not features.is_sod_or_later:
        return b"", b""
    return reader.bytes_(features.spells_bytes), reader.bytes_(features.skills_bytes)


def write_allowed_spells_skills(
    writer: BinaryWriter, spells: bytes, skills: bytes, features: MapFeatures
) -> None:
    if not features.is_sod_or_later:
        return
    writer.bytes_(spells)
    writer.bytes_(skills)


# --- слухи --------------------------------------------------------------


def read_rumors(reader: BinaryReader) -> list[Rumor]:
    count = reader.u32()
    if count > 1000:
        raise ValueError(f"неправдоподобное число слухов: {count}")
    return [Rumor(name=reader.string(), text=reader.string()) for _ in range(count)]


def write_rumors(writer: BinaryWriter, rumors: list[Rumor]) -> None:
    writer.u32(len(rumors))
    for rumor in rumors:
        writer.string(rumor.name)
        writer.string(rumor.text)
