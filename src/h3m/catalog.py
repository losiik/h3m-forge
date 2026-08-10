"""Заимствование объектов из карт поставки.

Ставить на карту объект — значит записать две вещи: шаблон (имя спрайта, маски
проходимости, допустимые рельефы) и начинку, своя у каждого типа. Обе можно
собрать по полям, и обе можно взять готовыми у авторов игры.

Здесь берём готовыми. Причина прагматичная: первая карта, собранная с нуля,
роняла редактор из-за трёх выдуманных значений, каждое из которых выглядело
разумным. Начинка объекта устроена сложнее заголовка, и вероятность повторить
ту же ошибку выше.

Поэтому объект переносится целиком, а правится в нём только то, что мы точно
понимаем — например, владелец города. Собирать начинку по полям будем позже и
по одному типу, сверяя каждый с редактором.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

from h3m import mapfile, paths
from h3m.container import read_map_bytes
from h3m.format import MapFormat
from h3m.instances import ObjectInstance
from h3m.objects import ObjectTemplate

log = logging.getLogger(__name__)


class NotFoundError(LookupError):
    """В картах поставки не нашлось подходящего объекта."""


@dataclass(slots=True)
class BorrowedObject:
    """Объект, взятый из настоящей карты целиком."""

    template: ObjectTemplate
    payload: bytes
    source: str
    """Имя карты, откуда взят — чтобы находка была воспроизводима."""

    def __str__(self) -> str:
        return f"{self.template} +{len(self.payload)}Б из «{self.source}»"


@lru_cache(maxsize=1)
def _sod_maps() -> tuple[str, ...]:
    """Имена карт SoD, разобранных до конца, от меньших к большим."""
    names = []
    for path in paths.iter_maps():
        parsed = mapfile.parse(read_map_bytes(path))
        if parsed.header.format is MapFormat.SOD and parsed.objects is not None:
            names.append(path.name)
    return tuple(names)


def borrow(
    object_id: int,
    *,
    subid: int | None = None,
    with_payload: bool | None = None,
) -> BorrowedObject:
    """Найти в картах поставки объект нужного типа и вернуть его целиком.

    :param object_id: тип объекта.
    :param subid: подтип, если важен (например, фракция города).
    :param with_payload: искать только объект с начинкой или только без неё.
    :raises NotFoundError: если такого объекта нет ни в одной карте.
    """
    for name in _sod_maps():
        parsed = mapfile.parse(read_map_bytes(paths.maps_dir() / name))
        assert parsed.objects is not None
        assert parsed.object_templates is not None

        for instance in parsed.objects:
            template = parsed.object_templates[instance.template_index]
            if template.object_id != object_id:
                continue
            if subid is not None and template.object_subid != subid:
                continue
            if with_payload is True and not instance.payload:
                continue
            if with_payload is False and instance.payload:
                continue

            borrowed = BorrowedObject(
                template=template, payload=instance.payload, source=name
            )
            log.debug("Заимствован %s", borrowed)
            return borrowed

    raise NotFoundError(
        f"в картах поставки не нашлось объекта id={object_id} subid={subid}"
    )


def place(
    parsed: mapfile.H3Map,
    borrowed: BorrowedObject,
    x: int,
    y: int,
    z: int = 0,
    *,
    payload: bytes | None = None,
) -> ObjectInstance:
    """Поставить заимствованный объект на карту.

    Шаблон добавляется в таблицу один раз: повторные постановки того же типа
    ссылаются на существующую запись, как это делают настоящие карты.
    """
    if parsed.object_templates is None or parsed.objects is None:
        raise ValueError("карта не содержит таблиц объектов")

    header = parsed.header
    if not (0 <= x < header.size and 0 <= y < header.size and 0 <= z < header.levels):
        raise ValueError(f"позиция ({x}, {y}, {z}) вне карты {header.size}x{header.size}")

    template_index = _template_index(parsed.object_templates, borrowed.template)

    instance = ObjectInstance(
        x=x,
        y=y,
        z=z,
        template_index=template_index,
        zeros=bytes(5),
        payload=borrowed.payload if payload is None else payload,
        object_id=borrowed.template.object_id,
    )
    parsed.objects.append(instance)
    return instance


def _template_index(
    templates: list[ObjectTemplate], template: ObjectTemplate
) -> int:
    for index, existing in enumerate(templates):
        if existing == template:
            return index
    templates.append(template)
    return len(templates) - 1


def borrow_decorations(
    limit: int, terrain: int, *, min_size: int = 1
) -> list[BorrowedObject]:
    """Набрать украшений, допустимых на данном рельефе.

    Берутся только объекты без начинки — деревья, камни, кусты. Это самая
    безопасная категория: ставить их можно куда угодно, и ничего, кроме
    шаблона, записывать не нужно.

    Проверка допустимости рельефа не формальность: у каждого шаблона своя
    маска, и ель, поставленная на воду, — не просто странно выглядящий тайл,
    а объект, которого игра там не ожидает.
    """
    found: list[BorrowedObject] = []
    seen: set[bytes] = set()

    for name in _sod_maps():
        parsed = mapfile.parse(read_map_bytes(paths.maps_dir() / name))
        assert parsed.objects is not None
        assert parsed.object_templates is not None

        for instance in parsed.objects:
            if instance.payload:
                continue
            template = parsed.object_templates[instance.template_index]
            if not template.allows_terrain(terrain):
                continue
            if len(template.blocked_cells()) < min_size:
                continue
            if template.animation_file in seen:
                continue

            seen.add(template.animation_file)
            found.append(
                BorrowedObject(template=template, payload=b"", source=name)
            )
            if len(found) >= limit:
                return found

    return found


def set_town_owner(payload: bytes, owner: int) -> bytes:
    """Сменить владельца города в заимствованной начинке.

    Начинка города начинается с четырёхбайтового идентификатора для квестов,
    сразу за ним — байт владельца. Это единственное, что мы здесь правим:
    остальное остаётся ровно таким, каким его записали авторы карты.
    """
    if len(payload) < 5:
        raise ValueError("начинка города короче ожидаемого")
    return payload[:4] + bytes([owner]) + payload[5:]
