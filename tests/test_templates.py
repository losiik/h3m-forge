"""Проверки таблицы шаблонов объектов."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from h3m import mapfile, paths
from h3m.objects import MASK_ROWS


def _maps() -> list[Path]:
    try:
        return list(paths.iter_maps())
    except paths.GameNotFoundError:
        return []


ALL_MAPS = _maps()

game_required = pytest.mark.skipif(
    not ALL_MAPS, reason="установка Heroes III не найдена (задайте H3_GAME_DIR)"
)

MAX_PLAUSIBLE_OBJECTS = 30_000


@game_required
@pytest.mark.parametrize("map_path", ALL_MAPS, ids=lambda p: p.name)
def test_objects_count_follows_templates(map_path: Path) -> None:
    """Сразу за таблицей шаблонов лежит правдоподобное число объектов."""
    parsed = mapfile.load(map_path)
    if parsed.object_templates is None:
        pytest.skip(f"разбор остановлен: {parsed.stopped_at}")

    assert len(parsed.tail) >= 4
    (objects_count,) = struct.unpack_from("<I", parsed.tail, 0)
    assert objects_count < MAX_PLAUSIBLE_OBJECTS


@game_required
def test_templates_look_like_sprites() -> None:
    """Имена спрайтов — непустые ASCII-строки с расширением .def.

    Сильная проверка интерпретации: имя читается как строка с длиной впереди,
    и если бы таблица шаблонов начиналась не там, вместо имён получился бы
    двоичный мусор.
    """
    for map_path in ALL_MAPS:
        parsed = mapfile.load(map_path)
        if parsed.object_templates is None:
            continue

        for template in parsed.object_templates:
            name = template.animation_text
            assert name, f"{map_path.name}: пустое имя спрайта"
            assert name.isascii(), f"{map_path.name}: не-ASCII имя {name!r}"
            assert name.lower().endswith(".def"), f"{map_path.name}: {name!r}"


@game_required
def test_template_masks_have_expected_width() -> None:
    """Обе маски занимают ровно по шесть байт."""
    for map_path in ALL_MAPS:
        parsed = mapfile.load(map_path)
        if parsed.object_templates is None:
            continue

        for template in parsed.object_templates:
            assert len(template.block_mask) == MASK_ROWS
            assert len(template.visit_mask) == MASK_ROWS


#: Идентификаторы объектов, которые обязаны занимать место на карте.
TOWN = 98
MONSTER = 54


@game_required
def test_block_mask_inversion_is_understood() -> None:
    """Бит проходимости инвертирован: ноль означает «занято».

    Проверяется с двух сторон, потому что односторонняя проверка тут ничего не
    доказывает:

    * города и монстры обязаны занимать хотя бы одну клетку — прочитай мы
      маску без инверсии, у них не оказалось бы ни одной;
    * при этом полностью проходимые шаблоны существовать должны: плоские
      декорации вроде святой земли (маска из одних единиц) не занимают ничего.
      Если бы таких не нашлось вовсе, это означало бы обратную ошибку.
    """
    fully_passable = 0
    checked_blocking = 0

    for map_path in ALL_MAPS:
        parsed = mapfile.load(map_path)
        if parsed.object_templates is None:
            continue

        for template in parsed.object_templates:
            if template.object_id in (TOWN, MONSTER):
                checked_blocking += 1
                assert template.blocked_cells(), (
                    f"{map_path.name}: {template.animation_text} "
                    f"(id={template.object_id}) не занимает ни одной клетки"
                )
            elif not template.blocked_cells():
                fully_passable += 1

    assert checked_blocking, "не нашлось ни городов, ни монстров"
    assert fully_passable, "не нашлось ни одного полностью проходимого шаблона"
