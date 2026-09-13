"""Discoverable MCP schema. Semantic checks remain in the dependency-free core."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

Stack = Annotated[list[int],Field(min_length=2,max_length=2)]
SevenResources = Annotated[list[int],Field(min_length=7,max_length=7)]


class StrictInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)


class RewardInput(StrictInput):
    army: list[Stack] = Field(default_factory=list,max_length=7)
    resources: SevenResources = Field(default_factory=lambda:[0]*7)
    artifacts: list[int] = Field(default_factory=list,max_length=8,description='IDs 10..51 except 36; travel artifacts excluded.')
    spells: list[int] = Field(default_factory=list,description='Combat spell IDs only; no adventure shortcuts.')
    experience: int = Field(default=0,ge=0,le=1000000)
    mana: int = Field(default=0,ge=0,le=1000)


class ChallengeInput(StrictInput):
    kind: Literal['visit','battle','resources','army','artifacts'] = 'visit'
    creature: int = Field(default=0,ge=0,le=65534)
    count: int = Field(default=1,ge=1,le=65535)
    resources: SevenResources = Field(default_factory=lambda:[0]*7)
    army: list[Stack] = Field(default_factory=list,max_length=7)
    artifacts: list[int] = Field(default_factory=list,max_length=8)
    text: str = Field(default='Завершите этот этап путешествия.',max_length=1800)
    auto_supply: bool = Field(default=True,description='Place enough local supplies for consumptive quests. If false, earlier mandatory rewards must suffice.')


class OpportunityInput(StrictInput):
    title: str = Field(min_length=1,max_length=80)
    text: str = Field(min_length=1,max_length=1800)
    guards: list[Stack] = Field(default_factory=list,max_length=7)
    reward: RewardInput = Field(default_factory=RewardInput)


class ChapterInput(StrictInput):
    id: str = Field(pattern='^[a-z][a-z0-9_]{0,31}$')
    title: str = Field(min_length=1,max_length=80)
    text: str = Field(min_length=1,max_length=1800)
    terrain: Literal['dirt','sand','grass','snow','swamp','rough','lava','highlands','wasteland'] = 'grass'
    requires: list[str] = Field(default_factory=list,max_length=4,description='ALL parent chapters must be complete. DAG only; no cycles.')
    optional: bool = False
    challenge: ChallengeInput = Field(default_factory=ChallengeInput)
    reward: RewardInput = Field(default_factory=RewardInput)
    opportunities: list[OpportunityInput] = Field(default_factory=list,max_length=2)
    sea_battle: list[Stack] = Field(default_factory=list,max_length=1)


class ScenarioInput(StrictInput):
    balance_profile: Literal['standard', 'fixed'] = Field(default='standard', description=
        'fixed: identical authored guards/rewards on 80/100/130/160/200%; no neutral growth, random upgrades, special months or town recruitment. Does not simulate combat or guarantee balance. standard preserves legacy behavior.')
    name: str = Field(min_length=1,max_length=128)
    description: str = Field(min_length=1,max_length=3000)
    chapters: list[ChapterInput] = Field(min_length=2,max_length=16)
    finale: str
    seed: int = Field(default=0,ge=-2147483648,le=2147483647)
    hero_name: str = Field(default='Путешественник',min_length=1,max_length=40)
    hero_biography: str = Field(default='',max_length=1800)
    army: list[Stack] = Field(default_factory=lambda:[[1,35],[3,25],[6,12]],min_length=1,max_length=7)
    spells: list[int] = Field(default_factory=lambda:[27,41,53,54])
    hero_skills: list[Stack] = Field(default_factory=lambda:[[0,3],[2,3],[5,3],[23,2],[22,2]],
        max_length=8,description='Complete starting secondary skills as [skill_id, level]. Replaces defaults. Query skill_catalog: Earth=17, Fire=14; levels 1..3. For permanent Resurrection use [17,2] or [17,3]; learning the spell also needs Wisdom [7,2]. Empty list means no skills.')
    max_travel: int = Field(default=65,ge=20,le=120,description='Maximum sea tiles per graph edge; compilation rejects longer routes.')
    decoration_density: float = Field(default=.4,ge=0,le=.65)
