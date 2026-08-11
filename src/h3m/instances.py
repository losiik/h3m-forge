"""Объекты, расставленные на карте.

Общая часть у всех одинакова: координаты, номер шаблона и пять нулевых байт.
Дальше идёт начинка, своя у каждого типа, и вот она — самая объёмная часть
формата: около тридцати разных раскладок.

Начинка хранится сырыми байтами вместе с распознанным типом. Для round-trip
достаточно правильно определить её **длину**; раскладывать на осмысленные поля
имеет смысл только для тех типов, которые понадобятся генератору, и это
отдельная задача.

Типы, для которых длина начинки пока не установлена, честно помечаются
неизвестными: разбор объектов останавливается, остаток уходит в хвост.
Гадать нельзя — ошибка в длине одного объекта сдвигает все последующие.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from h3m.format import MapFeatures, MapFormat
from h3m.heroes import PRIMARY_SKILLS, read_hero_artifacts
from h3m.objects import ObjectTemplate
from h3m.objtypes import (
    ARTIFACT_LIKE,
    BANK_LIKE,
    DWELLING_LIKE,
    GARRISON_LIKE,
    HERO_LIKE,
    MONSTER_LIKE,
    RESOURCE_LIKE,
    SHRINE_LIKE,
    SIGN_LIKE,
    TOWN_LIKE,
    Obj,
)
from h3m.options import UnsupportedBlockError
from h3m.stream import BinaryReader, BinaryWriter

log = logging.getLogger(__name__)

HEADER_ZEROS = 5
"""Нулевые байты между номером шаблона и начинкой."""

ARMY_SLOTS = 7
"""Слотов в наборе существ."""

RESOURCE_COUNT = 7
"""Дерево, ртуть, руда, сера, кристаллы, самоцветы, золото."""


@dataclass(slots=True)
class ObjectInstance:
    """Объект на карте."""

    x: int
    y: int
    z: int
    template_index: int
    zeros: bytes
    payload: bytes = b""

    object_id: int = -1
    """Тип из шаблона — для удобства, в файле его здесь нет."""

    @property
    def position(self) -> tuple[int, int, int]:
        return self.x, self.y, self.z

    def __str__(self) -> str:
        try:
            name = Obj(self.object_id).name
        except ValueError:
            name = f"id={self.object_id}"
        return f"{name} ({self.x}, {self.y}, {self.z}) +{len(self.payload)}Б"


class DriftError(UnsupportedBlockError):
    """Разбор объектов сбился: длина начинки предыдущего объекта неверна.

    Пять байт между номером шаблона и начинкой всегда нулевые, а номер шаблона
    обязан быть в границах таблицы. Нарушение любого из условий означает, что
    предыдущий объект прочитан на неверное число байт.
    """

    def __init__(
        self, ordinal: int, previous: ObjectInstance | None, zeros: bytes
    ) -> None:
        self.ordinal = ordinal
        self.previous = previous
        super().__init__(
            f"смещение уехало на объекте №{ordinal}; "
            f"предыдущий: {previous or 'нет'}; "
            f"байты выравнивания {zeros.hex(' ')}"
        )


class PayloadError(UnsupportedBlockError):
    """Начинка объекта разобрана неверно: раскладка для этого типа не сходится."""

    def __init__(
        self, object_id: int, subid: int, ordinal: int, cause: Exception
    ) -> None:
        self.object_id = object_id
        self.subid = subid
        self.ordinal = ordinal
        self.cause = cause
        super().__init__(
            f"начинка объекта id={object_id} subid={subid} "
            f"(№{ordinal}) не сходится: {type(cause).__name__}: {cause}"
        )


class UnknownObjectError(UnsupportedBlockError):
    """Длина начинки для этого типа объекта пока не установлена."""

    def __init__(self, object_id: int, subid: int, position: tuple[int, int, int]):
        self.object_id = object_id
        self.subid = subid
        self.position = position
        super().__init__(
            f"неизвестная начинка объекта id={object_id} subid={subid} "
            f"в позиции {position}"
        )


def _army_size(features: MapFeatures) -> int:
    """Длина набора существ: семь слотов по идентификатору и количеству."""
    return ARMY_SLOTS * (features.creature_id_bytes + 2)


def _read_message_and_guards(reader: BinaryReader, features: MapFeatures) -> None:
    """Пропустить общий блок «сообщение и охрана».

    Раскладка получена не дословно из исходников, а по классическому описанию
    формата, поэтому проверяется оракулом: если она неверна, разбор не придёт
    ровно в конец файла.
    """
    if not reader.u8():
        return

    reader.string()
    if reader.u8():
        reader.bytes_(_army_size(features))
    reader.bytes_(4)


def _read_payload(
    reader: BinaryReader,
    template: ObjectTemplate,
    features: MapFeatures,
    position: tuple[int, int, int],
) -> None:
    """Прочитать начинку объекта. Позиция читателя сдвигается на её длину."""
    object_id = template.object_id
    subid = template.object_subid

    if object_id in MONSTER_LIKE:
        if features.is_ab_or_later:
            reader.u32()  # идентификатор для квестов
        reader.u16()  # количество
        reader.u8()  # характер
        if reader.u8():  # есть сообщение
            reader.string()
            reader.bytes_(RESOURCE_COUNT * 4)
            # Здесь артефакт остаётся двухбайтовым даже в HotA. Расширение до
            # четырёх байт действует в квестах, наградах и содержимом ящика,
            # но не тут: попытка применить его и сюда дала 20 расхождений
            # по −2 на монстрах, которые до того сходились.
            reader.bytes_(features.artifact_id_bytes)
        reader.u8()  # никогда не бежит
        reader.u8()  # не растёт
        reader.bytes_(2)
        if features.hota_has_round_limit:
            reader.bytes_(4 + 1 + 4 + 4 + 4)
        if features.hota_has_recruitment_flags:
            reader.bytes_(1 + 4)
        return

    if object_id in SIGN_LIKE:
        reader.string()
        reader.bytes_(4)
        return

    if object_id in RESOURCE_LIKE:
        _read_message_and_guards(reader, features)
        reader.u32()  # количество
        reader.bytes_(4)
        return

    if object_id in ARTIFACT_LIKE:
        _read_message_and_guards(reader, features)
        if features.hota_has_recruitment_flags:
            reader.bytes_(4 + 1)  # режим подбора и флаги
        return

    if object_id == Obj.SPELL_SCROLL:
        _read_message_and_guards(reader, features)
        reader.bytes_(4)  # заклинание
        return

    if object_id == Obj.MINE:
        if subid < 7:
            reader.bytes_(4)  # владелец
        else:
            _read_abandoned_mine(reader, features)
        return

    if object_id == Obj.ABANDONED_MINE:
        _read_abandoned_mine(reader, features)
        return

    if object_id in DWELLING_LIKE:
        reader.bytes_(4)  # владелец
        return

    if object_id in SHRINE_LIKE:
        reader.bytes_(4)  # заклинание
        return

    if object_id in GARRISON_LIKE:
        reader.bytes_(4)  # владелец
        reader.bytes_(_army_size(features))
        if features.is_ab_or_later:
            reader.u8()  # можно ли забирать войска
        reader.bytes_(8)
        return

    if object_id in (Obj.SHIPYARD, Obj.LIGHTHOUSE):
        reader.bytes_(4)  # владелец
        return

    if object_id == Obj.GRAIL:
        if subid < 1000:
            reader.bytes_(4)  # радиус подсказки
            return
        raise UnknownObjectError(object_id, subid, position)  # место битвы HotA

    if object_id == Obj.WITCH_HUT:
        if features.is_ab_or_later:
            reader.bytes_(features.skills_bytes)
        return

    if object_id == Obj.SCHOLAR:
        reader.bytes_(1 + 1 + 6)  # тип награды, её номер, нули
        return

    if object_id in BANK_LIKE:
        if features.hota_has_round_limit:
            reader.i32()  # набор охраны
            reader.i8()  # присутствие улучшенных
            reader.bytes_(reader.u32() * 4)  # список артефактов
        return

    if object_id == Obj.PYRAMID:
        if features.hota_has_recruitment_flags:
            reader.bytes_(4 + 4)  # содержимое и заклинание
        return

    if object_id == Obj.UNIVERSITY or (
        object_id == Obj.HOTA_CUSTOM_OBJECT_2 and subid == 0
    ):
        # Мореходная академия HotA читается как университет.
        if features.hota_has_recruitment_flags:
            reader.bytes_(4 + features.skills_bytes)
        return

    if object_id == Obj.HOTA_CUSTOM_OBJECT_2:
        return  # прочие подтипы начинки не имеют

    if object_id == Obj.BLACK_MARKET:
        if features.hota_has_recruitment_flags:
            reader.bytes_(7 * (features.artifact_id_bytes + 2))
        return

    if object_id in _REWARD_WITH_ARTIFACT:
        # содержимое и либо артефакт, либо пропуск — в сумме всегда восемь байт
        if features.hota_has_recruitment_flags:
            reader.bytes_(8)
        return

    if object_id in _REWARD_WITH_GARBAGE:
        if features.hota_has_recruitment_flags:
            reader.bytes_(8)
        return

    if object_id in _REWARD_WITH_AMOUNT:
        _read_reward_with_amount(reader, features)
        return

    if object_id == Obj.HOTA_CUSTOM_OBJECT_1:
        # Лампа и бочка отдают ресурс с количеством, обломки и сосуд — нет.
        # Длины измерены на картах поставки: 18 байт против 8, и совпали
        # с раскладкой из исходников VCMI.
        if features.hota_has_recruitment_flags:
            if subid in (0, 1):
                reader.i32()
                reader.bytes_(14)
            else:
                reader.bytes_(8)
        return

    if object_id == Obj.HERO_PLACEHOLDER:
        _read_hero_placeholder(reader, features)
        return

    if object_id in _RANDOM_DWELLINGS:
        _read_random_dwelling(reader, features, object_id, subid)
        return

    if object_id in TOWN_LIKE:
        _read_town(reader, features)
        return

    if object_id in HERO_LIKE:
        _read_hero(reader, features)
        return

    if object_id == Obj.SEER_HUT:
        _read_seer_hut(reader, features)
        return

    if object_id == Obj.QUEST_GUARD:
        _read_quest(reader, features)
        return

    if object_id == Obj.PANDORAS_BOX:
        _read_box_content(reader, features)
        return

    if object_id == Obj.EVENT:
        _read_map_event_object(reader, features)
        return

    if object_id == Obj.BORDER_GATE:
        if subid == 1000:  # квестовые врата HotA
            _read_quest(reader, features)
            return
        if subid == 1001:  # могила HotA
            raise UnknownObjectError(object_id, subid, position)
        return  # обычные пограничные врата начинки не имеют

    if _has_no_payload(object_id, subid):
        return

    raise UnknownObjectError(object_id, subid, position)


#: Награды, где начинка — «что внутри» плюс необязательный артефакт.
_REWARD_WITH_ARTIFACT = frozenset(
    {
        Obj.TREASURE_CHEST,
        Obj.CORPSE,
        Obj.WARRIORS_TOMB,
        Obj.SHIPWRECK_SURVIVOR,
        Obj.SEA_CHEST,
    }
)

#: Награды без выбора содержимого.
_REWARD_WITH_GARBAGE = frozenset({Obj.FLOTSAM, Obj.TREE_OF_KNOWLEDGE})

#: Награды с количеством ресурсов.
_REWARD_WITH_AMOUNT = frozenset({Obj.CAMPFIRE, Obj.LEAN_TO, Obj.WAGON})

_RANDOM_DWELLINGS = frozenset(
    {Obj.RANDOM_DWELLING, Obj.RANDOM_DWELLING_LVL, Obj.RANDOM_DWELLING_FACTION}
)


def _read_reward_with_amount(reader: BinaryReader, features: MapFeatures) -> None:
    """Костёр, навес, повозка.

    Все три раскладки различаются составом полей, но не длиной: после
    четырёхбайтового «что внутри» идёт ровно четырнадцать байт начинки,
    независимо от того, награда это ресурсом, артефактом или ничем.
    """
    if not features.hota_has_recruitment_flags:
        return
    reader.i32()
    reader.bytes_(14)


def _read_hero_placeholder(reader: BinaryReader, features: MapFeatures) -> None:
    reader.u8()  # владелец
    hero_id = reader.u8()
    if hero_id == 0xFF:
        reader.u8()  # ранг силы вместо конкретного героя

    if features.hota_has_recruitment_flags:
        reader.u8()  # заданы ли стартовые войска
        reader.bytes_(7 * (4 + 4))  # количество и тип по слотам
        reader.bytes_(reader.i32() * 4)  # стартовые артефакты


def _quest_artifact_bytes(features: MapFeatures) -> int:
    """Ширина идентификатора артефакта в квестах и наградах.

    В HotA он четырёхбайтовый, тогда как в остальных местах формата остаётся
    двухбайтовым. Установлено измерением: награда-артефакт оказалась на шесть
    байт длиннее, чем в SoD, при том что все прочие награды — ровно на четыре.
    Разница в два байта и есть расширение идентификатора.
    """
    return 4 if features.is_hota else features.artifact_id_bytes


def _read_quest(reader: BinaryReader, features: MapFeatures) -> int:
    """Условие квеста: чего требует хижина провидца, страж или врата.

    Возвращает тип условия — он нужен вызывающему: тип 0 означает «условия
    нет», и тогда ни срока, ни текстов, ни награды не записано. Это
    единственное место в квестах, где отсутствие данных выражается не флагом,
    а значением типа.
    """
    mission = reader.u8()

    match mission:
        case 0:  # условия нет
            return mission
        case 1 | 3 | 4:  # уровень героя, убить героя, убить существо
            reader.bytes_(4)
        case 2:  # первичные навыки
            reader.bytes_(PRIMARY_SKILLS)
        case 5:  # принести артефакты
            reader.bytes_(reader.u8() * _quest_artifact_bytes(features))
        case 6:  # привести войско
            reader.bytes_(reader.u8() * (features.creature_id_bytes + 2))
        case 7:  # принести ресурсы
            reader.bytes_(RESOURCE_COUNT * 4)
        case 8 | 9:  # быть определённым героем, быть определённым игроком
            reader.u8()
        case _:
            raise ValueError(f"неизвестный тип квеста: {mission}")

    reader.bytes_(4)  # срок выполнения
    reader.string()  # текст при первом посещении
    reader.string()  # текст при повторном
    reader.string()  # текст по выполнении
    return mission


def _read_seer_hut(reader: BinaryReader, features: MapFeatures) -> None:
    """Хижина провидца: условие квеста и награда за него.

    В RoE общей структуры квеста ещё не было: там записан один байт с номером
    артефакта, а значение 255 означает «квеста нет». Ни срока выполнения, ни
    своих текстов в RoE у хижины нет — всё это появилось в AB вместе с полной
    системой квестов.
    """
    if features.is_hota:
        # Четырёхбайтовый префикс, на всех виденных картах равный единице.
        # Принадлежит именно хижине, а не квесту: у стража квеста и у врат
        # запись начинается сразу с типа условия — проверено по байтам.
        # Пока префикс читался внутри квеста, стражи разбирались неверно.
        reader.u32()

    if features.is_ab_or_later:
        mission = _read_quest(reader, features)
    else:
        mission = 0 if reader.u8() == 0xFF else 5

    if mission == 0:
        reader.bytes_(3)
        return

    reward = reader.u8()

    # HotA добавил типы наград сверх известных десяти — встречался тип 15.
    # Была гипотеза, что запись награды у него стала фиксированной, 13 байт
    # независимо от типа: измерение на четырёх случаях дало ровно 13 и для
    # типа 0, и для типа 15. Проверка не подтвердила — ошибок на хижинах стало
    # 7 вместо 8, зато на монстрах 21 вместо 17, то есть они просто переехали.
    # Четырёх наблюдений мало; оставляю честную ошибку вместо догадки.

    match reward:
        case 0:  # без награды
            pass
        case 1 | 2:  # опыт, мана
            reader.bytes_(4)
        case 3 | 4:  # боевой дух, удача
            reader.u8()
        case 5:  # ресурсы
            reader.u8()
            reader.bytes_(4)
        case 6 | 7:  # первичный навык, вторичный навык
            reader.bytes_(2)
        case 8:  # артефакт
            reader.bytes_(_quest_artifact_bytes(features))
        case 9:  # заклинание
            reader.u8()
        case 10:  # существа
            reader.bytes_(features.creature_id_bytes + 2)
        case _:
            raise ValueError(f"неизвестный тип награды: {reward}")

    # Хвост записи награды: два байта в SoD, шесть в HotA. Измерено на шести
    # типах наград сразу — все оказались длиннее ровно на четыре байта.
    reader.bytes_(6 if features.is_hota else 2)


def _read_box_content(reader: BinaryReader, features: MapFeatures) -> None:
    """Содержимое ящика Пандоры — оно же начинка события на карте."""
    _read_message_and_guards(reader, features)

    reader.bytes_(4)  # опыт
    reader.bytes_(4)  # мана
    reader.i8()  # боевой дух
    reader.i8()  # удача
    reader.bytes_(RESOURCE_COUNT * 4)  # ресурсы
    reader.bytes_(PRIMARY_SKILLS)  # первичные навыки

    reader.bytes_(reader.u8() * 2)  # вторичные навыки
    reader.bytes_(reader.u8() * _quest_artifact_bytes(features))  # артефакты
    reader.bytes_(reader.u8())  # заклинания
    reader.bytes_(reader.u8() * (features.creature_id_bytes + 2))  # существа

    reader.bytes_(8)

    if features.is_hota:
        # Четырнадцать байт, назначение не установлено.
        #
        # Измерено независимо на двух типах, использующих это содержимое:
        # ящику Пандоры не хватало ровно +14, событию +13 — разница в единицу
        # объяснилась лишним байтом, который я добавлял событию по подсказке
        # из чужого кода. Совпадение двух независимых измерений и есть
        # подтверждение.
        #
        # Часть записей (шесть ящиков и шесть событий из сотни) требует ещё
        # двух байт. Признак, по которому они отличаются, не установлен;
        # попытка сделать 16 байт для всех ухудшила результат вчетверо, так
        # что это именно вариант, а не общее правило.
        reader.bytes_(14)


def _read_map_event_object(reader: BinaryReader, features: MapFeatures) -> None:
    """Событие, расставленное на карте: содержимое ящика плюс правила срабатывания."""
    _read_box_content(reader, features)
    reader.u8()  # каких игроков касается
    reader.u8()  # срабатывает ли у ИИ
    reader.u8()  # исчезает ли после посещения
    reader.bytes_(4)


SPELLS_MASK = 9
"""Байт на маску заклинаний: 70 заклинаний."""


def _read_town(reader: BinaryReader, features: MapFeatures) -> None:
    """Город — самая объёмная начинка: гарнизон, постройки, заклинания, события."""
    if features.is_ab_or_later:
        reader.u32()  # идентификатор для квестов

    reader.u8()  # владелец
    if reader.u8():  # своё название
        reader.string()

    if reader.u8():  # свой гарнизон
        reader.bytes_(_army_size(features))

    reader.u8()  # построение войск

    if reader.u8():  # заданы постройки
        reader.bytes_(features.buildings_mask_bytes)  # построенные
        reader.bytes_(features.buildings_mask_bytes)  # запрещённые
    else:
        reader.u8()  # есть ли форт

    if features.is_ab_or_later:
        reader.bytes_(SPELLS_MASK)  # обязательные заклинания
    reader.bytes_(SPELLS_MASK)  # возможные заклинания

    if features.hota_has_mirror_arena:
        # Два байта. Первый — флаг доступности исследования заклинаний,
        # назначение второго не установлено. Длина найдена не подгонкой:
        # проверялось, что сразу за городом начинается корректный заголовок
        # следующего объекта, и только два байта дают это на 51 городе из 53.
        reader.bytes_(2)

    for _ in range(reader.u32()):  # события города
        reader.string()  # название
        reader.string()  # текст
        reader.bytes_(RESOURCE_COUNT * 4)  # ресурсы
        reader.u8()  # каких игроков касается
        if features.is_sod_or_later:
            reader.u8()  # касается ли людей
        reader.u8()  # касается ли ИИ
        reader.u16()  # первое срабатывание
        reader.u8()  # период повтора
        reader.bytes_(17)
        reader.bytes_(features.buildings_mask_bytes)  # новые постройки
        reader.bytes_(RESOURCE_COUNT * 2)  # прирост существ
        reader.bytes_(4)

    if features.is_sod_or_later:
        reader.u8()  # мировоззрение
    reader.bytes_(3)

    if features.is_hota:
        # Пять байт в самом конце записи города. Назначение не установлено.
        #
        # Найдены перебором, но это не подгонка: при +5 разбор проходит 24905
        # объектов, при любом другом значении от 0 до 15 — около 2985.
        # Восьмикратный отрыв одного значения от всех соседних — это сигнал,
        # а не случайное совпадение: подгонка выглядит как плато, а не как пик.
        reader.bytes_(5)


def _read_hero(reader: BinaryReader, features: MapFeatures) -> None:
    """Герой на карте, а также темница и случайный герой."""
    if features.is_ab_or_later:
        reader.u32()  # идентификатор для квестов

    reader.u8()  # владелец
    reader.u8()  # тип героя

    if reader.u8():  # своё имя
        reader.string()

    if features.is_sod_or_later:
        if reader.u8():  # задан опыт
            reader.u32()
    else:
        reader.u32()  # в RoE и AB опыт пишется всегда

    if reader.u8():  # свой портрет
        reader.u8()

    if reader.u8():  # заданы вторичные навыки
        reader.bytes_(reader.u32() * 2)

    if reader.u8():  # свой гарнизон
        reader.bytes_(_army_size(features))

    reader.u8()  # построение войск
    read_hero_artifacts(reader, features)
    reader.u8()  # радиус патрулирования

    if features.is_ab_or_later:
        if reader.u8():  # своя биография
            reader.string()
        reader.u8()  # пол

    if features.is_sod_or_later:
        if reader.u8():  # свои заклинания
            reader.bytes_(SPELLS_MASK)
    elif features.format is MapFormat.AB:
        reader.u8()  # в AB можно задать одно заклинание

    if features.is_sod_or_later:
        if reader.u8():  # свои первичные навыки
            reader.bytes_(PRIMARY_SKILLS)

    reader.bytes_(16)

    if features.is_hota:
        # Шесть байт, назначение не установлено. Измерено на девяти героях
        # разных подтипов в шести картах — везде ровно +6.
        reader.bytes_(6)


def _read_random_dwelling(
    reader: BinaryReader, features: MapFeatures, object_id: int, subid: int
) -> None:
    reader.bytes_(4)  # владелец

    has_faction = object_id in (Obj.RANDOM_DWELLING, Obj.RANDOM_DWELLING_LVL)
    has_level = object_id in (Obj.RANDOM_DWELLING, Obj.RANDOM_DWELLING_FACTION)

    if has_faction and reader.u32() == 0:
        # ноль означает «фракция задана маской», иначе привязка к другому объекту
        reader.bytes_(features.faction_mask_bytes)

    if has_level:
        reader.bytes_(2)  # минимальный и максимальный уровень


def _read_abandoned_mine(reader: BinaryReader, features: MapFeatures) -> None:
    reader.bytes_(4)  # маска ресурсов
    if features.hota_has_recruitment_flags:
        if reader.u8():
            reader.bytes_(4 + 4 + 4)  # существо, минимум, максимум
        else:
            reader.bytes_(12)


#: Типы с собственной начинкой, длина которой ещё не установлена.
#: Список сокращается по мере разбора; порядок работ задаёт
#: tools/object_coverage.py — по числу карт, которые тип разблокирует.
_TYPES_WITH_UNKNOWN_PAYLOAD: frozenset[int] = frozenset()


def _has_no_payload(object_id: int, subid: int) -> bool:
    """Читается ли объект как обычный, без собственной начинки."""
    return object_id not in _TYPES_WITH_UNKNOWN_PAYLOAD


def read_objects(
    reader: BinaryReader, templates: list[ObjectTemplate], features: MapFeatures
) -> list[ObjectInstance]:
    """Прочитать список расставленных объектов."""
    count = reader.u32()
    if count > 30_000:
        raise ValueError(f"неправдоподобное число объектов: {count}")

    instances: list[ObjectInstance] = []
    for ordinal in range(count):
        x, y, z = reader.u8(), reader.u8(), reader.u8()
        template_index = reader.u32()
        zeros = reader.bytes_(HEADER_ZEROS)

        if template_index >= len(templates) or any(zeros):
            # Смещение уехало. Виноват не этот объект, а предыдущий: длина его
            # начинки посчитана неверно. Сообщаем именно о нём — иначе поиск
            # придётся вести вслепую.
            raise DriftError(ordinal, instances[-1] if instances else None, zeros)

        template = templates[template_index]
        start = reader.pos
        try:
            _read_payload(reader, template, features, (x, y, z))
        except UnsupportedBlockError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Любая поломка внутри начинки означает неверную её раскладку.
            # Оборачиваем, чтобы разбор остановился штатно и было видно, на
            # каком именно типе объекта мы не правы.
            raise PayloadError(template.object_id, template.object_subid, ordinal, exc)

        instances.append(
            ObjectInstance(
                x=x,
                y=y,
                z=z,
                template_index=template_index,
                zeros=zeros,
                payload=reader.data[start : reader.pos],
                object_id=template.object_id,
            )
        )

    log.debug("Объектов: %d", len(instances))
    return instances


def write_objects(writer: BinaryWriter, instances: list[ObjectInstance]) -> None:
    """Зеркало read_objects."""
    writer.u32(len(instances))
    for instance in instances:
        writer.u8(instance.x)
        writer.u8(instance.y)
        writer.u8(instance.z)
        writer.u32(instance.template_index)
        writer.bytes_(instance.zeros)
        writer.bytes_(instance.payload)
