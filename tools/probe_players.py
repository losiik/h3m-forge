"""Ручной разбор блока игроков на конкретной карте.

Когда парсер уезжает, отчёты по всей поставке бесполезны — нужно смотреть
байты одной карты и сверять с тем, что мы думаем о формате. Скрипт печатает
область игроков в hex с пометками, где парсер считает границы полей.

Запуск:
    python tools/probe_players.py "Freedom.h3m"
"""

from __future__ import annotations

import logging
import sys

from h3m import paths
from h3m.container import read_map_bytes
from h3m.header import read_header
from h3m.logging_setup import setup_logging
from h3m.players import PLAYER_COUNT, _read_player  # noqa: PLC2701 — отладочный доступ
from h3m.stream import BinaryReader

log = logging.getLogger("probe_players")


def hexdump(data: bytes, start: int, length: int, *, marks: dict[int, str]) -> None:
    end = min(start + length, len(data))
    for line_start in range(start, end, 16):
        chunk = data[line_start : min(line_start + 16, end)]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        note = marks.get(line_start, "")
        log.info("  %5d: %-47s %s", line_start, hex_part, note)


def main() -> None:
    setup_logging("probe_players")

    name = sys.argv[1] if len(sys.argv) > 1 else "Freedom.h3m"
    path = paths.maps_dir() / name
    if not path.exists():
        log.error("Нет такой карты: %s", path)
        return

    data = read_map_bytes(path)
    reader = BinaryReader(data)
    header = read_header(reader)

    log.info("Карта: %s", name)
    log.info("Заголовок: %s", header)
    log.info("Признаки: AB+=%s SoD+=%s маска фракций=%d байт, огрызок=%d байт",
             header.features.is_ab_or_later,
             header.features.is_sod_or_later,
             header.features.faction_mask_bytes,
             header.features.unplayable_player_padding)
    log.info("Блок игроков начинается с байта %d", reader.pos)

    marks: dict[int, str] = {}
    players_start = reader.pos

    for index in range(PLAYER_COUNT):
        start = reader.pos
        try:
            player = _read_player(reader, header.features, index)
        except Exception as exc:  # noqa: BLE001
            log.error("Игрок %d (с байта %d): %s: %s", index, start,
                      type(exc).__name__, exc)
            marks[start - start % 16] = f"<- игрок {index}: ОШИБКА"
            break
        log.info("Игрок %d: байты %d..%d (%d) — %s",
                 index, start, reader.pos - 1, reader.pos - start, player)
        marks[start - start % 16] = f"<- игрок {index}"

    log.info("")
    log.info("Байты области игроков:")
    hexdump(data, players_start, 320, marks=marks)


if __name__ == "__main__":
    main()
