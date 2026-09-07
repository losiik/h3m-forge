"""Сборка начинки объектов.

До сих пор объекты только заимствовались целиком из чужих карт — так было
безопаснее, но не позволяло задать содержимое. Здесь начинка собирается по
полям, и это первый раз, когда мы пишем в файл структуру, а не копию.

Каждый сборщик проверяется собственным читателем: собранные байты обязаны
разобраться ровно и без остатка. Это тот же round-trip, только на уровне
одного объекта, и он ловит расхождение сборщика с читателем немедленно.

Значения по умолчанию извлечены из карт поставки, а не выбраны из общих
соображений — привычка, которая за этот проект окупилась трижды.
"""

from __future__ import annotations

import logging

from h3m.format import MapFeatures
from h3m.stream import BinaryWriter

log = logging.getLogger(__name__)

RESOURCE_COUNT = 7

SIGN_RESERVED = 4
"""Нулевые байты после текста таблички. Ровно четыре на всех 76 табличках SoD."""

DEFAULT_CHARACTER = 2
"""Характер монстра: 2 у 3580 монстров из 4978, самый частый."""

MONSTER_RESERVED = 2


class Character:
    """Насколько охотно монстр присоединяется к герою."""

    COMPLIANT = 0
    FRIENDLY = 1
    AGGRESSIVE = 2
    HOSTILE = 3
    SAVAGE = 4


def quest_identifier(x: int, y: int, z: int) -> int:
    """Псевдослучайный идентификатор монстра, выводимый из координат.

    В картах поставки это поле ненулевое **у всех** 4978 монстров, так что
    нули туда писать нельзя. Но и настоящая случайность не годится: карта
    должна собираться байт в байт при каждом запуске, иначе теряется
    воспроизводимость. Поэтому число выводится из координат.
    """
    mixed = (x * 73_856_093) ^ (y * 19_349_663) ^ ((z + 1) * 83_492_791)
    return mixed & 0xFFFFFFFF


PRIMARY_SKILLS = 4
BOX_RESERVED = 8

NO_QUEST_LIMIT = 0xFFFFFFFF
"""Срок выполнения квеста: «без ограничения»."""


class Mission:
    """Тип условия квеста."""

    NONE = 0
    HERO_LEVEL = 1
    ARTIFACTS = 5


class Reward:
    """Тип награды за квест."""

    NOTHING = 0
    EXPERIENCE = 1
    ARTIFACT = 8


def pandora_payload(
    features: MapFeatures,
    *,
    message: bytes | None = None,
    experience: int = 0,
    mana: int = 0,
    morale: int = 0,
    luck: int = 0,
    resources: tuple[int, ...] = (),
    artifacts: tuple[int, ...] = (),
    spells: tuple[int, ...] = (),
) -> bytes:
    """Ящик Пандоры: награда, выдаваемая при посещении.

    Существа и вторичные навыки пока не поддержаны — на карте они не нужны,
    а поддерживать непроверенное значит копить долг.
    """
    writer = BinaryWriter()

    writer.u8(1 if message is not None else 0)
    if message is not None:
        writer.string(message)
        writer.u8(0)  # охраны нет
        writer.bytes_(bytes(4))

    writer.u32(experience)
    writer.u32(mana)
    writer.i8(morale)
    writer.i8(luck)

    padded = tuple(resources) + (0,) * (RESOURCE_COUNT - len(resources))
    for amount in padded[:RESOURCE_COUNT]:
        writer.u32(amount)
    writer.bytes_(bytes(PRIMARY_SKILLS))

    writer.u8(0)  # вторичные навыки

    writer.u8(len(artifacts))
    for artifact in artifacts:
        writer.bytes_(artifact.to_bytes(features.artifact_id_bytes, "little"))

    writer.u8(len(spells))
    for spell in spells:
        writer.u8(spell)

    writer.u8(0)  # существа
    writer.bytes_(bytes(BOX_RESERVED))

    return writer.getvalue()


def _write_quest_texts(
    writer: BinaryWriter, first: bytes, repeat: bytes, done: bytes
) -> None:
    writer.u32(NO_QUEST_LIMIT)
    writer.string(first)
    writer.string(repeat)
    writer.string(done)


def quest_guard_payload(
    features: MapFeatures,
    *,
    artifact: int,
    first: bytes,
    repeat: bytes = b"",
    done: bytes = b"",
) -> bytes:
    """Страж квеста, пропускающий только с нужным артефактом."""
    writer = BinaryWriter()
    writer.u8(Mission.ARTIFACTS)
    writer.u8(1)
    writer.bytes_(artifact.to_bytes(features.artifact_id_bytes, "little"))
    _write_quest_texts(writer, first, repeat, done)
    return writer.getvalue()


def seer_hut_artifact_payload(
    features: MapFeatures,
    *,
    artifact: int,
    first: bytes,
    repeat: bytes = b"",
    done: bytes = b"",
) -> bytes:
    """Хижина провидца, выдающая артефакт.

    Условием стоит первый уровень героя — то есть выполнимо всегда. Совсем без
    условия нельзя: тип 0 означает «квеста нет», и тогда формат не хранит
    награду вовсе.
    """
    writer = BinaryWriter()
    writer.u8(Mission.HERO_LEVEL)
    writer.u32(1)
    _write_quest_texts(writer, first, repeat, done)

    writer.u8(Reward.ARTIFACT)
    writer.bytes_(artifact.to_bytes(features.artifact_id_bytes, "little"))
    writer.bytes_(bytes(2))
    return writer.getvalue()


def sign_payload(text: bytes) -> bytes:
    """Табличка или бутылка с посланием: текст и четыре нуля."""
    writer = BinaryWriter()
    writer.string(text)
    writer.bytes_(bytes(SIGN_RESERVED))
    return writer.getvalue()


def monster_payload(
    features: MapFeatures,
    *,
    position: tuple[int, int, int],
    count: int,
    character: int = DEFAULT_CHARACTER,
    message: bytes | None = None,
    resources: tuple[int, ...] = (),
    artifact: int | None = None,
    never_flees: bool = False,
    not_growing: bool = False,
) -> bytes:
    """Отряд монстров.

    ``count`` равный нулю означает «случайное количество по силе карты» —
    так поступает и редактор, когда число не задано вручную.
    """
    if message is None and (resources or artifact is not None):
        raise ValueError("награда за бой задаётся только вместе с сообщением")

    writer = BinaryWriter()

    if features.is_ab_or_later:
        writer.u32(quest_identifier(*position))

    writer.u16(count)
    writer.u8(character)

    writer.u8(1 if message is not None else 0)
    if message is not None:
        writer.string(message)
        padded = tuple(resources) + (0,) * (RESOURCE_COUNT - len(resources))
        for amount in padded[:RESOURCE_COUNT]:
            writer.u32(amount)
        writer.bytes_(
            (artifact if artifact is not None else 0xFFFF).to_bytes(
                features.artifact_id_bytes, "little"
            )
        )

    writer.u8(1 if never_flees else 0)
    writer.u8(1 if not_growing else 0)
    writer.bytes_(bytes(MONSTER_RESERVED))

    return writer.getvalue()
