"""Explicit output schemas for the game encyclopedia's MCP tools."""
from typing import Literal
from typing import Any
from pydantic import BaseModel, ConfigDict

Category=Literal['artifacts','creatures','spells']
Ruleset=Literal['hota_1.8.0','hota_1.8.1']


class Contract(BaseModel):
    model_config=ConfigDict(extra='forbid')


class ScenarioSupport(Contract):
    status: Literal['supported','unsupported','requires_reference_template']
    reason: str


class Summary(Contract):
    category: Category
    id: int
    key: str
    name_ru: str
    name_en: str
    summary: str
    tags: list[str]
    reference_ruleset: str
    target_ruleset: str
    hota_runtime: Literal['not_verified']
    scenario_support: ScenarioSupport


class SearchResult(Contract):
    catalog_version: str
    ruleset: Ruleset
    items: list[Summary]
    total: int
    offset: int
    next_offset: int | None
    coverage: dict[str,int]
    limitations: list[str]


class Source(Contract):
    id: str
    kind: Literal['vcmi','local_reference_table','local_game_data','official_documentation','official_changelog','community_reference']
    location: str
    revision: str
    sha256: str
    fields: str


class Verification(Contract):
    native_id: Literal['verified_against_pinned_reference']
    properties: Literal['reference_only','reference_with_documented_hota_changes','official_documentation_and_native_data']
    hota_runtime: Literal['not_verified']
    unknown_fields: list[str]


class Effect(Contract):
    key: str
    type: str
    subtype: str | None
    value: int | float | None
    scope: str | None
    value_type: str | None
    description: str | None = None
    parameters: dict[str,Any] = {}
    source_artifact_id: int | None = None


class Cost(Contract):
    wood: int
    mercury: int
    ore: int
    sulfur: int
    crystal: int
    gems: int
    gold: int


class Creature(Contract):
    faction: str
    level: int
    attack: int
    defense: int
    hit_points: int
    speed: int
    damage_min: int
    damage_max: int
    shots: int
    growth: int
    cost: Cost
    ai_value: int | None
    upgrades: list[int]
    effects: list[Effect]
    fight_value: int | None = None
    horde_growth: int | None = None
    map_amount_min: int | None = None
    map_amount_max: int | None = None


class Artifact(Contract):
    slot: list[str]
    cost_gold: int
    artifact_class: str
    effects: list[Effect]
    components: list[int] | None
    component_effects: list[Effect] = []
    effects_include_components: bool = False
    assembly_slots: dict[str,int] = {}
    effective_primary_skills: dict[str,int] = {}
    effective_daily_income: dict[str,int] = {}
    default_availability: str = 'not_verified'


class SpellLevel(Contract):
    mastery: Literal['none','basic','advanced','expert']
    mana_cost: int
    mass: bool
    formula: str | None
    value: int | None
    unit: str | None
    permanent_resurrection: bool | None


class Prerequisite(Contract):
    skill_id: int
    minimum_level: int
    purpose: str


class Spell(Contract):
    level: int
    schools: list[str]
    target: str
    levels: list[SpellLevel]
    prerequisites: list[Prerequisite]
    restrictions: list[str]
    counters: list[str]


class Card(Contract):
    category: Category
    id: int
    key: str
    name_ru: str
    name_en: str
    aliases: list[str]
    summary: str
    tags: list[str]
    reference_ruleset: str
    target_ruleset: str
    verification: Verification
    source_ids: list[str]
    version_notes: list[str] = []
    scenario_support: ScenarioSupport
    creature: Creature | None
    artifact: Artifact | None
    spell: Spell | None


class GetResult(Contract):
    catalog_version: str
    ruleset: Ruleset
    found: bool
    item: Card | None
    sources: list[Source]
    message: str
    limitations: list[str]
