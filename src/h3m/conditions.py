"""Условия победы и поражения.

Тринадцать типов победы и три поражения, у каждого своя начинка переменной
длины. Начинка хранится сырыми байтами: разбирать её на осмысленные поля
понадобится только при генерации карт, а для round-trip достаточно знать
длину. Длина же зависит от версии — идентификаторы артефактов и существ
занимают байт в RoE и два начиная с AB.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum

from h3m.format import MapFeatures
from h3m.stream import BinaryReader, BinaryWriter

log = logging.getLogger(__name__)

#: «Обычное» условие — победить всех противников, без дополнительных полей.
STANDARD = 0xFF


class VictoryType(IntEnum):
    """Тип условия победы."""

    ARTIFACT = 0
    """Добыть артефакт."""

    GATHER_TROOP = 1
    """Накопить существ определённого типа."""

    GATHER_RESOURCE = 2
    """Накопить ресурс."""

    BUILD_CITY = 3
    """Отстроить город."""

    BUILD_GRAIL = 4
    """Построить Грааль."""

    BEAT_HERO = 5
    """Победить героя."""

    CAPTURE_CITY = 6
    """Захватить город."""

    BEAT_MONSTER = 7
    """Убить монстра."""

    TAKE_DWELLINGS = 8
    """Занять все жилища существ."""

    TAKE_MINES = 9
    """Занять все шахты."""

    TRANSPORT_ITEM = 10
    """Доставить артефакт в город."""

    HOTA_ELIMINATE_MONSTERS = 11
    """Истребить всех монстров (HotA)."""

    HOTA_SURVIVE_DAYS = 12
    """Продержаться заданное число дней (HotA)."""


class LossType(IntEnum):
    """Тип условия поражения."""

    LOSE_TOWN = 0
    LOSE_HERO = 1
    TIME_EXPIRES = 2


@dataclass(slots=True)
class VictoryCondition:
    """Условие победы: тип, два флага и сырая начинка."""

    kind: int
    allow_normal_victory: int = 0
    applies_to_ai: int = 0
    payload: bytes = b""

    @property
    def is_standard(self) -> bool:
        return self.kind == STANDARD

    def __str__(self) -> str:
        if self.is_standard:
            return "обычная победа"
        try:
            return VictoryType(self.kind).name
        except ValueError:
            return f"неизвестный тип {self.kind}"


@dataclass(slots=True)
class LossCondition:
    """Условие поражения: тип и сырая начинка."""

    kind: int
    payload: bytes = b""

    @property
    def is_standard(self) -> bool:
        return self.kind == STANDARD

    def __str__(self) -> str:
        if self.is_standard:
            return "обычное поражение"
        try:
            return LossType(self.kind).name
        except ValueError:
            return f"неизвестный тип {self.kind}"


def _victory_payload_size(kind: int, features: MapFeatures) -> int:
    """Длина начинки условия победы в байтах."""
    match kind:
        case VictoryType.ARTIFACT:
            return features.artifact_id_bytes
        case VictoryType.GATHER_TROOP:
            return features.creature_id_bytes + 4
        case VictoryType.GATHER_RESOURCE:
            return 1 + 4
        case VictoryType.BUILD_CITY:
            # координаты города плюс требуемые уровни ратуши и форта
            return 3 + 1 + 1
        case (
            VictoryType.BUILD_GRAIL
            | VictoryType.BEAT_HERO
            | VictoryType.CAPTURE_CITY
            | VictoryType.BEAT_MONSTER
        ):
            return 3
        case VictoryType.TAKE_DWELLINGS | VictoryType.TAKE_MINES:
            return 0
        case VictoryType.TRANSPORT_ITEM:
            # здесь артефакт всегда однобайтовый, независимо от версии
            return 1 + 3
        case VictoryType.HOTA_ELIMINATE_MONSTERS:
            return 0
        case VictoryType.HOTA_SURVIVE_DAYS:
            return 4
        case _:
            raise ValueError(f"неизвестный тип условия победы: {kind}")


def _loss_payload_size(kind: int) -> int:
    """Длина начинки условия поражения в байтах."""
    match kind:
        case LossType.LOSE_TOWN | LossType.LOSE_HERO:
            return 3
        case LossType.TIME_EXPIRES:
            return 2
        case _:
            raise ValueError(f"неизвестный тип условия поражения: {kind}")


def read_victory(reader: BinaryReader, features: MapFeatures) -> VictoryCondition:
    kind = reader.u8()
    if kind == STANDARD:
        return VictoryCondition(kind=kind)

    condition = VictoryCondition(
        kind=kind,
        allow_normal_victory=reader.u8(),
        applies_to_ai=reader.u8(),
    )
    condition.payload = reader.bytes_(_victory_payload_size(kind, features))
    log.debug("Условие победы: %s", condition)
    return condition


def write_victory(
    writer: BinaryWriter, condition: VictoryCondition, features: MapFeatures
) -> None:
    writer.u8(condition.kind)
    if condition.is_standard:
        return
    writer.u8(condition.allow_normal_victory)
    writer.u8(condition.applies_to_ai)
    writer.bytes_(condition.payload)


def read_loss(reader: BinaryReader) -> LossCondition:
    kind = reader.u8()
    if kind == STANDARD:
        return LossCondition(kind=kind)

    condition = LossCondition(kind=kind, payload=reader.bytes_(_loss_payload_size(kind)))
    log.debug("Условие поражения: %s", condition)
    return condition


def write_loss(writer: BinaryWriter, condition: LossCondition) -> None:
    writer.u8(condition.kind)
    if condition.is_standard:
        return
    writer.bytes_(condition.payload)
