"""Карта целиком: разбор и сборка.

Приём, на котором держится вся стратегия разработки: то, что ещё не разобрано
на поля, хранится **хвостом сырых байтов** и пишется обратно как есть.

Следствия приятные:

* побайтовый round-trip проходит с самого первого дня, когда разобран один
  только заголовок. Значит, регрессия в уже понятой части ловится немедленно,
  а не через неделю;
* метрикой прогресса становится не «работает / не работает», а доля файла,
  разобранная на поля. Число, которое растёт;
* можно двигаться по формату последовательно, не блокируясь на непонятном
  куске: непонятое просто остаётся в хвосте.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from h3m.container import read_map_bytes, write_map_bytes
from h3m.header import MapHeader, read_header, write_header
from h3m.players import PlayerInfo, read_players, write_players
from h3m.stream import BinaryReader, BinaryWriter

log = logging.getLogger(__name__)


@dataclass(slots=True)
class H3Map:
    """Разобранная карта."""

    header: MapHeader
    players: list[PlayerInfo] = field(default_factory=list)

    tail: bytes = b""
    """Ещё не разобранная часть файла. Пишется обратно без изменений."""

    total_size: int = 0
    """Размер распакованного файла — чтобы считать долю разобранного."""

    @property
    def parsed_size(self) -> int:
        return self.total_size - len(self.tail)

    @property
    def parsed_fraction(self) -> float:
        return self.parsed_size / self.total_size if self.total_size else 0.0

    @property
    def playable_players(self) -> list[PlayerInfo]:
        return [player for player in self.players if player.is_playable]


def parse(data: bytes) -> H3Map:
    """Разобрать распакованную карту настолько, насколько умеем."""
    reader = BinaryReader(data)

    header = read_header(reader)
    players = read_players(reader, header.features)

    parsed = H3Map(
        header=header,
        players=players,
        tail=reader.bytes_(reader.remaining),
        total_size=len(data),
    )
    reader.expect_end()

    log.debug(
        "Разобрано %d из %d байт (%.1f%%)",
        parsed.parsed_size,
        parsed.total_size,
        parsed.parsed_fraction * 100,
    )
    return parsed


def serialize(parsed: H3Map) -> bytes:
    """Собрать карту обратно в распакованный поток."""
    writer = BinaryWriter()

    write_header(writer, parsed.header)
    write_players(writer, parsed.players, parsed.header.features)
    writer.bytes_(parsed.tail)

    return writer.getvalue()


def load(path: Path) -> H3Map:
    """Прочитать карту с диска."""
    return parse(read_map_bytes(path))


def save(path: Path, parsed: H3Map) -> None:
    """Записать карту на диск."""
    write_map_bytes(path, serialize(parsed))
