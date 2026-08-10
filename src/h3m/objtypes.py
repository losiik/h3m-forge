"""Идентификаторы типов объектов.

Значения общие для всех версий формата; HotA добавляет свои в свободные
номера. Перечислены не все существующие типы, а те, что нужны разбору:
у остальных нет собственной начинки, и они читаются как обычные.
"""

from __future__ import annotations

from enum import IntEnum


class Obj(IntEnum):
    """Тип объекта — поле id в шаблоне."""

    ARTIFACT = 5
    PANDORAS_BOX = 6
    BLACK_MARKET = 7
    CAMPFIRE = 12
    CREATURE_BANK = 16
    CREATURE_GENERATOR1 = 17
    CREATURE_GENERATOR2 = 18
    CREATURE_GENERATOR3 = 19
    CREATURE_GENERATOR4 = 20
    CORPSE = 22
    DERELICT_SHIP = 24
    DRAGON_UTOPIA = 25
    EVENT = 26
    EYE_OF_MAGI = 27
    FAERIE_RING = 28
    FLOTSAM = 29
    GARRISON = 33
    HERO = 34
    GRAIL = 36
    LEAN_TO = 39
    LIGHTHOUSE = 42
    MINE = 53
    MONSTER = 54
    OCEAN_BOTTLE = 59
    PRISON = 62
    PYRAMID = 63
    RANDOM_ART = 65
    RANDOM_TREASURE_ART = 66
    RANDOM_MINOR_ART = 67
    RANDOM_MAJOR_ART = 68
    RANDOM_RELIC_ART = 69
    RANDOM_HERO = 70
    RANDOM_MONSTER = 71
    RANDOM_MONSTER_L1 = 72
    RANDOM_MONSTER_L2 = 73
    RANDOM_MONSTER_L3 = 74
    RANDOM_MONSTER_L4 = 75
    RANDOM_RESOURCE = 76
    RANDOM_TOWN = 77
    RESOURCE = 79
    SCHOLAR = 81
    SEA_CHEST = 82
    SEER_HUT = 83
    CRYPT = 84
    SHIPWRECK = 85
    SHIPWRECK_SURVIVOR = 86
    SHIPYARD = 87
    SHRINE_OF_MAGIC_INCANTATION = 88
    SHRINE_OF_MAGIC_GESTURE = 89
    SHRINE_OF_MAGIC_THOUGHT = 90
    SIGN = 91
    SPELL_SCROLL = 93
    TOWN = 98
    TREASURE_CHEST = 101
    TREE_OF_KNOWLEDGE = 102
    UNIVERSITY = 104
    WAGON = 105
    WARRIORS_TOMB = 108
    WITCH_HUT = 113
    RANDOM_MONSTER_L5 = 162
    RANDOM_MONSTER_L6 = 163
    RANDOM_MONSTER_L7 = 164
    BORDER_GATE = 212
    HERO_PLACEHOLDER = 214
    QUEST_GUARD = 215
    RANDOM_DWELLING = 216
    RANDOM_DWELLING_LVL = 217
    RANDOM_DWELLING_FACTION = 218
    GARRISON2 = 219
    ABANDONED_MINE = 220


#: Типы, читающиеся как обычные: собственной начинки у них нет.
HERO_LIKE = frozenset({Obj.HERO, Obj.RANDOM_HERO, Obj.PRISON})

MONSTER_LIKE = frozenset(
    {
        Obj.MONSTER,
        Obj.RANDOM_MONSTER,
        Obj.RANDOM_MONSTER_L1,
        Obj.RANDOM_MONSTER_L2,
        Obj.RANDOM_MONSTER_L3,
        Obj.RANDOM_MONSTER_L4,
        Obj.RANDOM_MONSTER_L5,
        Obj.RANDOM_MONSTER_L6,
        Obj.RANDOM_MONSTER_L7,
    }
)

ARTIFACT_LIKE = frozenset(
    {
        Obj.ARTIFACT,
        Obj.RANDOM_ART,
        Obj.RANDOM_TREASURE_ART,
        Obj.RANDOM_MINOR_ART,
        Obj.RANDOM_MAJOR_ART,
        Obj.RANDOM_RELIC_ART,
    }
)

RESOURCE_LIKE = frozenset({Obj.RESOURCE, Obj.RANDOM_RESOURCE})

TOWN_LIKE = frozenset({Obj.TOWN, Obj.RANDOM_TOWN})

DWELLING_LIKE = frozenset(
    {
        Obj.CREATURE_GENERATOR1,
        Obj.CREATURE_GENERATOR2,
        Obj.CREATURE_GENERATOR3,
        Obj.CREATURE_GENERATOR4,
    }
)

SHRINE_LIKE = frozenset(
    {
        Obj.SHRINE_OF_MAGIC_INCANTATION,
        Obj.SHRINE_OF_MAGIC_GESTURE,
        Obj.SHRINE_OF_MAGIC_THOUGHT,
    }
)

BANK_LIKE = frozenset(
    {
        Obj.CREATURE_BANK,
        Obj.DERELICT_SHIP,
        Obj.DRAGON_UTOPIA,
        Obj.CRYPT,
        Obj.SHIPWRECK,
    }
)

SIGN_LIKE = frozenset({Obj.SIGN, Obj.OCEAN_BOTTLE})

GARRISON_LIKE = frozenset({Obj.GARRISON, Obj.GARRISON2})
