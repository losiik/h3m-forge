"""Версии формата .h3m и их отличия.

Формат развивался надстройками: каждое дополнение добавляло поля, не меняя
уже существующие. Поэтому парсер строится не как «четыре разных парсера», а
как один, спрашивающий у набора признаков, есть ли в этой версии такое поле.

Числовые характеристики (сколько героев, артефактов, навыков) нужны потому,
что в файле лежат битовые маски разрешённого — их длина зависит от версии.
Ошибка в этих числах немедленно сдвинет все последующие смещения.

Источник значений — исходники VCMI (lib/mapping/MapFeaturesH3M.cpp), сверено
с реальными картами из поставки HotA 1.8.0.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class MapFormat(IntEnum):
    """Значение первого поля файла — версии формата."""

    ROE = 0x0E
    """Restoration of Erathia — базовая игра."""

    AB = 0x15
    """Armageddon's Blade — первое дополнение."""

    SOD = 0x1C
    """Shadow of Death — второе дополнение, самый распространённый формат."""

    HOTA = 0x20
    """Horn of the Abyss — фанатское дополнение, свои поля в заголовке."""

    WOG = 0x33
    """In the Wake of Gods."""

    @property
    def title(self) -> str:
        return _FORMAT_TITLES[self]


_FORMAT_TITLES = {
    MapFormat.ROE: "Restoration of Erathia",
    MapFormat.AB: "Armageddon's Blade",
    MapFormat.SOD: "Shadow of Death",
    MapFormat.HOTA: "Horn of the Abyss",
    MapFormat.WOG: "In the Wake of Gods",
}


@dataclass(frozen=True, slots=True)
class MapFeatures:
    """Что доступно в конкретной версии формата.

    ``hota_level`` — подверсия HotA (поле сразу за версией). Возможности HotA
    добавлялись постепенно, и часть полей заголовка появляется только начиная
    с определённой подверсии.
    """

    format: MapFormat
    hota_level: int = 0

    terrains: int = 10
    factions: int = 9
    heroes: int = 156
    artifacts: int = 144
    spells: int = 70
    skills: int = 28

    # --- признаки наличия полей ----------------------------------------

    @property
    def is_hota(self) -> bool:
        return self.format is MapFormat.HOTA

    @property
    def has_level_limit(self) -> bool:
        """Ограничение уровня героев — появилось в AB."""
        return self.format is not MapFormat.ROE

    @property
    def is_ab_or_later(self) -> bool:
        """AB и всё, что появилось после: SoD, WoG, HotA."""
        return self.format is not MapFormat.ROE

    @property
    def is_sod_or_later(self) -> bool:
        """SoD и всё, что появилось после: WoG, HotA."""
        return self.format in (MapFormat.SOD, MapFormat.WOG, MapFormat.HOTA)

    @property
    def faction_mask_bytes(self) -> int:
        """Ширина битовой маски разрешённых фракций.

        В RoE фракций восемь и маска умещается в байт. Начиная с AB фракций
        девять, и поле расширили до двух байт; HotA с его двенадцатью
        фракциями в те же два байта укладывается.
        """
        return 1 if self.format is MapFormat.ROE else 2

    @property
    def unplayable_player_padding(self) -> int:
        """Сколько байт занимает огрызок игрока, за которого нельзя играть.

        Значения накопительные, и это главная ловушка места. В VCMI код выглядит
        как три подряд идущих условия, а не как выбор одного из трёх::

            if(features.levelROE) reader->skipUnused(6);
            if(features.levelAB)  reader->skipUnused(6);
            if(features.levelSOD) reader->skipUnused(1);

        У AB-карты истинны и levelROE, и levelAB, поэтому пропускается 12 байт,
        а не 6. Прочитать это как взаимоисключающие ветки — и половина карт
        перестаёт разбираться.
        """
        if self.format is MapFormat.ROE:
            return 6
        if self.format is MapFormat.AB:
            return 12
        return 13

    @property
    def hota_has_mirror_arena(self) -> bool:
        """Флаги зеркальной и арена-карты (levelHOTA1)."""
        return self.is_hota and self.hota_level > 0

    @property
    def hota_has_terrain_count(self) -> bool:
        """Число типов террейна в заголовке (levelHOTA2)."""
        return self.is_hota and self.hota_level > 1

    @property
    def hota_has_town_count(self) -> bool:
        """Число фракций и маска доступных сложностей (levelHOTA5)."""
        return self.is_hota and self.hota_level > 4

    @property
    def hota_has_defeated_heroes(self) -> bool:
        """Найм побеждённых героев (levelHOTA7)."""
        return self.is_hota and self.hota_level > 6

    @property
    def hota_has_version_triplet(self) -> bool:
        """Тройка major/minor/patch версии HotA (levelHOTA8).

        Проверено на картах HotA 1.8.0 (подверсия 9): тройка лежит сразу за
        подверсией, до всех остальных HotA-полей. Порядок полей в файле не
        совпадает с порядком появления возможностей — это стоит помнить.
        """
        return self.is_hota and self.hota_level > 7

    @property
    def hota_has_unknown_i32(self) -> bool:
        """Поле неизвестного назначения (levelHOTA9). На наших картах всегда 0."""
        return self.is_hota and self.hota_level > 8

    @property
    def hota_has_combined_artifacts(self) -> bool:
        """Запрет составных артефактов (levelHOTA1)."""
        return self.is_hota and self.hota_level > 0

    @property
    def hota_has_round_limit(self) -> bool:
        """Ограничение числа раундов (levelHOTA3)."""
        return self.is_hota and self.hota_level > 2

    @property
    def hota_has_recruitment_flags(self) -> bool:
        """Запрет найма героев по игрокам, 8 флагов (levelHOTA5)."""
        return self.is_hota and self.hota_level > 4

    @property
    def hota_has_scripts(self) -> bool:
        """Собственная система событий HotA (levelHOTA9)."""
        return self.is_hota and self.hota_level > 8

    # --- ширины идентификаторов -----------------------------------------

    @property
    def artifact_id_bytes(self) -> int:
        """Идентификатор артефакта: байт в RoE, два начиная с AB."""
        return 2 if self.is_ab_or_later else 1

    @property
    def creature_id_bytes(self) -> int:
        """Идентификатор существа: байт в RoE, два начиная с AB."""
        return 2 if self.is_ab_or_later else 1

    @property
    def artifact_slots(self) -> int:
        """Слотов снаряжения у героя. SoD добавил девятнадцатый."""
        return 19 if self.is_sod_or_later else 18

    @property
    def hero_slot_has_scroll_spell(self) -> bool:
        """С подверсии HotA 5 к каждому слоту добавлены два байта под свиток."""
        return self.is_hota and self.hota_level > 4

    # --- длины битовых масок --------------------------------------------

    @staticmethod
    def _mask_bytes(count: int) -> int:
        return (count + 7) // 8

    @property
    def heroes_bytes(self) -> int:
        return self._mask_bytes(self.heroes)

    @property
    def artifacts_bytes(self) -> int:
        return self._mask_bytes(self.artifacts)

    @property
    def spells_bytes(self) -> int:
        return self._mask_bytes(self.spells)

    @property
    def skills_bytes(self) -> int:
        return self._mask_bytes(self.skills)


def features_for(format_: MapFormat, hota_level: int = 0) -> MapFeatures:
    """Собрать набор признаков для версии формата.

    Числа для HotA зависят от подверсии: фракции и герои добавлялись по мере
    выхода обновлений (Причал, затем Фабрика).
    """
    if format_ is MapFormat.ROE:
        return MapFeatures(format_, terrains=10, factions=8, heroes=128,
                           artifacts=127, spells=70, skills=28)
    if format_ is MapFormat.AB:
        return MapFeatures(format_, terrains=10, factions=9, heroes=156,
                           artifacts=129, spells=70, skills=28)
    if format_ is MapFormat.SOD:
        return MapFeatures(format_, terrains=10, factions=9, heroes=156,
                           artifacts=144, spells=70, skills=28)
    if format_ is MapFormat.WOG:
        return MapFeatures(format_, terrains=10, factions=9, heroes=156,
                           artifacts=171, spells=70, skills=28)

    # HotA: пороги подверсий взяты из MapFeaturesH3M.cpp
    if hota_level > 6:
        return MapFeatures(format_, hota_level, terrains=12, factions=12,
                           heroes=215, artifacts=166, spells=70, skills=30)
    if hota_level > 4:
        return MapFeatures(format_, hota_level, terrains=12, factions=11,
                           heroes=198, artifacts=166, spells=70, skills=29)
    return MapFeatures(format_, hota_level, terrains=12, factions=10,
                       heroes=178, artifacts=163, spells=70, skills=29)
