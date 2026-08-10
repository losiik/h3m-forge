"""Глобальные события карты — последний блок файла.

Срабатывают по календарю, а не по посещению: «на 7-й день все игроки получают
1000 золота, далее каждые 14 дней». Расставленные на карте события (объект
типа EVENT) — совсем другая сущность, они лежат среди объектов.

За событиями до конца файла остаётся хвост нулей, который игра не читает.
Его длина не постоянна, поэтому храним как есть.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from h3m.format import MapFeatures
from h3m.stream import BinaryReader, BinaryWriter, decode

log = logging.getLogger(__name__)

RESOURCE_COUNT = 7
RESERVED = 17
"""Нулевые байты в конце записи события."""


@dataclass(slots=True)
class TimedEvent:
    """Событие, срабатывающее в заданный день."""

    name: bytes
    message: bytes
    resources: bytes
    players: int
    human_affected: int
    computer_affected: int
    first_day: int
    repeat_days: int
    reserved: bytes

    @property
    def name_text(self) -> str:
        return decode(self.name)

    @property
    def message_text(self) -> str:
        return decode(self.message)

    def __str__(self) -> str:
        repeat = f", каждые {self.repeat_days} дн." if self.repeat_days else ""
        return f"«{self.name_text}» на {self.first_day + 1}-й день{repeat}"


@dataclass(slots=True)
class EventsBlock:
    """Все глобальные события плюс хвост файла."""

    events: list[TimedEvent] = field(default_factory=list)
    trailing: bytes = b""
    """Хвост нулей до конца файла — игрой не используется."""


def read_events(reader: BinaryReader, features: MapFeatures) -> EventsBlock:
    """Прочитать блок глобальных событий и остаток файла."""
    count = reader.u32()
    if count > 1000:
        raise ValueError(f"неправдоподобное число событий: {count}")

    events = [
        TimedEvent(
            name=reader.string(),
            message=reader.string(),
            resources=reader.bytes_(RESOURCE_COUNT * 4),
            players=reader.u8(),
            human_affected=reader.u8() if features.is_sod_or_later else 1,
            computer_affected=reader.u8(),
            first_day=reader.u16(),
            repeat_days=reader.u8(),
            reserved=reader.bytes_(RESERVED),
        )
        for _ in range(count)
    ]

    block = EventsBlock(events=events, trailing=reader.bytes_(reader.remaining))
    log.debug("Глобальных событий: %d, хвост %d байт", len(events), len(block.trailing))
    return block


def write_events(
    writer: BinaryWriter, block: EventsBlock, features: MapFeatures
) -> None:
    """Зеркало read_events."""
    writer.u32(len(block.events))
    for event in block.events:
        writer.string(event.name)
        writer.string(event.message)
        writer.bytes_(event.resources)
        writer.u8(event.players)
        if features.is_sod_or_later:
            writer.u8(event.human_affected)
        writer.u8(event.computer_affected)
        writer.u16(event.first_day)
        writer.u8(event.repeat_days)
        writer.bytes_(event.reserved)

    writer.bytes_(block.trailing)
