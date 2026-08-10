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

Последнее работает и внутри одного прогона: если блок встретился в состоянии,
которое мы разбирать не умеем, разбор откатывается к границе этого блока, и
остаток честно уходит в хвост. Ни угадывания, ни потери round-trip.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from h3m import conditions, options
from h3m.container import read_map_bytes, write_map_bytes
from h3m.header import MapHeader, read_header, write_header
from h3m.heroes import PredefinedHeroes, read_predefined_heroes, write_predefined_heroes
from h3m.objects import ObjectTemplate, read_object_templates, write_object_templates
from h3m.players import PlayerInfo, read_players, write_players
from h3m.stream import BinaryReader, BinaryWriter
from h3m.terrain import TerrainMap, read_terrain, write_terrain

log = logging.getLogger(__name__)


@dataclass(slots=True)
class H3Map:
    """Разобранная карта."""

    header: MapHeader
    players: list[PlayerInfo] = field(default_factory=list)

    victory: conditions.VictoryCondition | None = None
    loss: conditions.LossCondition | None = None
    meta: options.MapMeta | None = None
    predefined_heroes: PredefinedHeroes | None = None
    terrain: TerrainMap | None = None
    object_templates: list[ObjectTemplate] | None = None

    tail: bytes = b""
    """Ещё не разобранная часть файла. Пишется обратно без изменений."""

    total_size: int = 0
    """Размер распакованного файла — чтобы считать долю разобранного."""

    stopped_at: str | None = None
    """Почему разбор остановился раньше, если остановился."""

    @property
    def parsed_size(self) -> int:
        return self.total_size - len(self.tail)

    @property
    def parsed_fraction(self) -> float:
        return self.parsed_size / self.total_size if self.total_size else 0.0

    @property
    def playable_players(self) -> list[PlayerInfo]:
        return [player for player in self.players if player.is_playable]


def _read_meta(reader: BinaryReader, header: MapHeader) -> options.MapMeta:
    """Прочитать всё между условиями победы и предустановленными героями."""
    features = header.features

    teams = options.read_teams(reader)
    allowed_heroes, placeholders = options.read_allowed_heroes(reader, features)
    disposed = options.read_disposed_heroes(reader, features)
    map_options = options.read_map_options(reader, features)
    scripts_flag = options.read_hota_scripts(reader, features)
    allowed_artifacts = options.read_allowed_artifacts(reader, features)
    allowed_spells, allowed_skills = options.read_allowed_spells_skills(reader, features)
    rumors = options.read_rumors(reader)

    return options.MapMeta(
        teams=teams,
        allowed_heroes=allowed_heroes,
        hero_placeholders=placeholders,
        disposed_heroes=disposed,
        options=map_options,
        hota_scripts_flag=scripts_flag,
        allowed_artifacts=allowed_artifacts,
        allowed_spells=allowed_spells,
        allowed_skills=allowed_skills,
        rumors=rumors,
    )


def _write_meta(writer: BinaryWriter, meta: options.MapMeta, header: MapHeader) -> None:
    """Зеркало _read_meta."""
    features = header.features

    options.write_teams(writer, meta.teams)
    options.write_allowed_heroes(
        writer, meta.allowed_heroes, meta.hero_placeholders, features
    )
    options.write_disposed_heroes(writer, meta.disposed_heroes, features)
    options.write_map_options(writer, meta.options, features)
    options.write_hota_scripts(writer, meta.hota_scripts_flag)
    options.write_allowed_artifacts(writer, meta.allowed_artifacts, features)
    options.write_allowed_spells_skills(
        writer, meta.allowed_spells, meta.allowed_skills, features
    )
    options.write_rumors(writer, meta.rumors)


def parse(data: bytes) -> H3Map:
    """Разобрать распакованную карту настолько, насколько умеем."""
    reader = BinaryReader(data)

    header = read_header(reader)
    players = read_players(reader, header.features)

    parsed = H3Map(header=header, players=players, total_size=len(data))

    parsed.victory = conditions.read_victory(reader, header.features)
    parsed.loss = conditions.read_loss(reader)

    boundary = reader.pos
    try:
        parsed.meta = _read_meta(reader, header)
        parsed.predefined_heroes = read_predefined_heroes(reader, header.features)
        parsed.terrain = read_terrain(reader, header.size, header.levels)
        parsed.object_templates = read_object_templates(reader)
    except options.UnsupportedBlockError as exc:
        # Откатываемся к началу блока: пусть остаток честно лежит хвостом.
        reader.pos = boundary
        parsed.meta = None
        parsed.predefined_heroes = None
        parsed.terrain = None
        parsed.object_templates = None
        parsed.stopped_at = str(exc)
        log.debug("Разбор остановлен на байте %d: %s", boundary, exc)

    parsed.tail = reader.bytes_(reader.remaining)
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

    if parsed.victory is not None:
        conditions.write_victory(writer, parsed.victory, parsed.header.features)
    if parsed.loss is not None:
        conditions.write_loss(writer, parsed.loss)
    if parsed.meta is not None:
        _write_meta(writer, parsed.meta, parsed.header)
    if parsed.predefined_heroes is not None:
        write_predefined_heroes(writer, parsed.predefined_heroes, parsed.header.features)
    if parsed.terrain is not None:
        write_terrain(writer, parsed.terrain)
    if parsed.object_templates is not None:
        write_object_templates(writer, parsed.object_templates)

    writer.bytes_(parsed.tail)
    return writer.getvalue()


def load(path: Path) -> H3Map:
    """Прочитать карту с диска."""
    return parse(read_map_bytes(path))


def save(path: Path, parsed: H3Map) -> None:
    """Записать карту на диск."""
    write_map_bytes(path, serialize(parsed))
