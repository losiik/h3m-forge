"""Предустановленные герои — заданные картой характеристики конкретных героев.

Блок появился в SoD. Идёт перебором по всем героям игры: у каждого один байт
«настроен ли», и только для настроенных читается начинка. На типичной карте
настроены единицы, поэтому блок обычно вырождается в длинную череду нулей —
но длина этой череды зависит от числа героев в версии, а у HotA оно вдобавок
записано в самом файле.

Начинка героя хранится разобранной по полям, но содержимое слотов снаряжения
и масок оставлено сырыми байтами: для round-trip достаточно знать длину,
а осмысленный разбор понадобится только при генерации.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from h3m.format import MapFeatures
from h3m.stream import BinaryReader, BinaryWriter, decode

log = logging.getLogger(__name__)

PRIMARY_SKILLS = 4
"""Нападение, защита, сила магии, знание."""


@dataclass(slots=True)
class HeroArtifacts:
    """Снаряжение героя: слоты и рюкзак."""

    present: int = 0
    slots: bytes = b""
    backpack_count: int = 0
    backpack: bytes = b""


@dataclass(slots=True)
class PredefinedHero:
    """Герой с заданными картой характеристиками."""

    hero_id: int

    experience: int | None = None
    secondary_skills: bytes | None = None
    artifacts: HeroArtifacts = field(default_factory=HeroArtifacts)
    biography: bytes | None = None
    gender: int = 0xFF
    spells: bytes | None = None
    primary_skills: bytes | None = None

    @property
    def biography_text(self) -> str:
        return decode(self.biography) if self.biography else ""


@dataclass(slots=True)
class PredefinedHeroes:
    """Весь блок предустановленных героев."""

    declared_count: int | None = None
    """Число героев, записанное в файле. Есть только у HotA."""

    heroes: dict[int, PredefinedHero] = field(default_factory=dict)
    """Только настроенные герои, по их номеру."""

    hota_extra: bytes = b""
    """Дополнительные флаги HotA: по шесть байт на каждого героя."""


def _slot_size(features: MapFeatures) -> int:
    """Длина одной записи слота снаряжения."""
    size = features.artifact_id_bytes
    if features.hero_slot_has_scroll_spell:
        size += 2
    return size


def _read_artifacts(reader: BinaryReader, features: MapFeatures) -> HeroArtifacts:
    artifacts = HeroArtifacts(present=reader.u8())
    if not artifacts.present:
        return artifacts

    slot = _slot_size(features)
    artifacts.slots = reader.bytes_(features.artifact_slots * slot)
    artifacts.backpack_count = reader.u16()
    artifacts.backpack = reader.bytes_(artifacts.backpack_count * slot)
    return artifacts


def _write_artifacts(
    writer: BinaryWriter, artifacts: HeroArtifacts, features: MapFeatures
) -> None:
    writer.u8(artifacts.present)
    if not artifacts.present:
        return
    writer.bytes_(artifacts.slots)
    writer.u16(artifacts.backpack_count)
    writer.bytes_(artifacts.backpack)


def read_predefined_heroes(
    reader: BinaryReader, features: MapFeatures
) -> PredefinedHeroes:
    """Прочитать блок предустановленных героев."""
    if not features.is_sod_or_later:
        return PredefinedHeroes()

    result = PredefinedHeroes()
    if features.is_hota:
        result.declared_count = reader.u32()
        count = result.declared_count
    else:
        count = features.heroes

    for hero_id in range(count):
        if not reader.u8():
            continue

        hero = PredefinedHero(hero_id=hero_id)

        if reader.u8():
            hero.experience = reader.u32()

        if reader.u8():
            skill_count = reader.u32()
            hero.secondary_skills = reader.bytes_(skill_count * 2)

        hero.artifacts = _read_artifacts(reader, features)

        if reader.u8():
            hero.biography = reader.string()

        hero.gender = reader.u8()

        if reader.u8():
            hero.spells = reader.bytes_(features.spells_bytes)

        if reader.u8():
            hero.primary_skills = reader.bytes_(PRIMARY_SKILLS)

        result.heroes[hero_id] = hero

    if features.hota_has_recruitment_flags:
        # по шесть байт на героя: два флага и уровень
        result.hota_extra = reader.bytes_(count * 6)

    log.debug("Предустановленных героев: %d из %d", len(result.heroes), count)
    return result


def write_predefined_heroes(
    writer: BinaryWriter, block: PredefinedHeroes, features: MapFeatures
) -> None:
    """Зеркало read_predefined_heroes."""
    if not features.is_sod_or_later:
        return

    if features.is_hota:
        writer.u32(block.declared_count or 0)
        count = block.declared_count or 0
    else:
        count = features.heroes

    for hero_id in range(count):
        hero = block.heroes.get(hero_id)
        if hero is None:
            writer.u8(0)
            continue

        writer.u8(1)

        writer.u8(1 if hero.experience is not None else 0)
        if hero.experience is not None:
            writer.u32(hero.experience)

        writer.u8(1 if hero.secondary_skills is not None else 0)
        if hero.secondary_skills is not None:
            writer.u32(len(hero.secondary_skills) // 2)
            writer.bytes_(hero.secondary_skills)

        _write_artifacts(writer, hero.artifacts, features)

        writer.u8(1 if hero.biography is not None else 0)
        if hero.biography is not None:
            writer.string(hero.biography)

        writer.u8(hero.gender)

        writer.u8(1 if hero.spells is not None else 0)
        if hero.spells is not None:
            writer.bytes_(hero.spells)

        writer.u8(1 if hero.primary_skills is not None else 0)
        if hero.primary_skills is not None:
            writer.bytes_(hero.primary_skills)

    if features.hota_has_recruitment_flags:
        writer.bytes_(block.hota_extra)
