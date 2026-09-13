"""Strict, dependency-free input contract for authored HotA adventures."""
from dataclasses import dataclass, field, asdict
import re

from h3m.terrain import Terrain
from h3m.skills import DEFAULT_HERO_SKILLS, validate_skill_pairs

COMBAT_SPELLS = {10, 15, 16, 17, 18, 19, 20, 21, 22, 23, 26, 27, 28, 29,
                 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43,
                 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56}
SOILS = {t.name.lower() for t in Terrain if t not in (Terrain.WATER, Terrain.ROCK, Terrain.SUBTERRANEAN)}


def integer(value, lo, hi, label):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f'{label}: expected integer {lo}..{hi}')


def message(value, label, maximum=1800, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()) or len(value)>maximum:
        raise ValueError(f'{label}: invalid text (maximum {maximum} characters)')
    value.encode('cp1251')


def stacks(value, label, empty=True):
    if not isinstance(value, (list, tuple)) or len(value)>7 or (not empty and not value):
        raise ValueError(f'{label}: provide 1..7 stacks')
    seen=set()
    for unit in value:
        if not isinstance(unit,(list,tuple)) or len(unit)!=2:
            raise ValueError(f'{label}: stack must be [creature_id, count]')
        creature,count=unit
        integer(creature,0,65534,label); integer(count,1,65535,label)
        if creature in seen: raise ValueError(f'{label}: duplicate creature')
        seen.add(creature)


def resources(value, label):
    if not isinstance(value,(list,tuple)) or len(value)!=7:
        raise ValueError(f'{label}: seven resources required (wood..gold)')
    for amount in value: integer(amount,0,1000000,label)


@dataclass
class RewardSpec:
    army: list = field(default_factory=list)
    resources: list = field(default_factory=lambda:[0]*7)
    artifacts: list = field(default_factory=list)
    spells: list = field(default_factory=list)
    experience: int = 0
    mana: int = 0

    def validate(self):
        stacks(self.army,'reward.army'); resources(self.resources,'reward.resources')
        for a in self.artifacts: integer(a,10,51,'reward.artifacts')
        if 36 in self.artifacts: raise ValueError('Artifact 36 is reserved for victory')
        if len(self.artifacts)>8: raise ValueError('At most eight reward artifacts')
        if len(set(self.spells))!=len(self.spells) or not set(self.spells)<=COMBAT_SPELLS:
            raise ValueError('Only unique supported combat spells are allowed')
        for s in self.spells: integer(s,0,69,'spell')
        integer(self.experience,0,1000000,'experience'); integer(self.mana,0,1000,'mana')


@dataclass
class Challenge:
    kind: str = 'visit'
    creature: int = 0
    count: int = 1
    resources: list = field(default_factory=lambda:[0]*7)
    army: list = field(default_factory=list)
    artifacts: list = field(default_factory=list)
    text: str = 'Завершите этот этап путешествия.'
    auto_supply: bool = True

    def validate(self):
        if self.kind not in ('visit','battle','resources','army','artifacts'):
            raise ValueError('challenge.kind: visit/battle/resources/army/artifacts')
        message(self.text,'challenge.text'); integer(self.creature,0,65534,'creature')
        integer(self.count,1,65535,'count'); resources(self.resources,'challenge.resources')
        stacks(self.army,'challenge.army')
        for a in self.artifacts: integer(a,10,51,'challenge.artifacts')
        if 36 in self.artifacts: raise ValueError('Artifact 36 is reserved for victory')
        if len(self.artifacts)>8: raise ValueError('At most eight required artifacts')
        if type(self.auto_supply) is not bool: raise ValueError('auto_supply must be boolean')
        if self.kind=='resources' and not any(self.resources): raise ValueError('Resource quest is empty')
        if self.kind=='army' and not self.army: raise ValueError('Army quest is empty')
        if self.kind=='artifacts' and not self.artifacts: raise ValueError('Artifact quest is empty')
        if self.kind!='resources' and any(self.resources): raise ValueError('Unused challenge resources')
        if self.kind!='army' and self.army: raise ValueError('Unused challenge army')
        if self.kind!='artifacts' and self.artifacts: raise ValueError('Unused challenge artifacts')


@dataclass
class Opportunity:
    title: str
    text: str
    guards: list = field(default_factory=list)
    reward: RewardSpec = field(default_factory=RewardSpec)


@dataclass
class Chapter:
    id: str
    title: str
    text: str
    terrain: str = 'grass'
    requires: list = field(default_factory=list)
    optional: bool = False
    challenge: Challenge = field(default_factory=Challenge)
    reward: RewardSpec = field(default_factory=RewardSpec)
    opportunities: list = field(default_factory=list)
    sea_battle: list = field(default_factory=list)


@dataclass
class ScenarioSpec:
    name: str
    description: str
    chapters: list
    finale: str
    seed: int = 0
    hero_name: str = 'Путешественник'
    hero_biography: str = ''
    army: list = field(default_factory=lambda:[[1,35],[3,25],[6,12]])
    spells: list = field(default_factory=lambda:[27,41,53,54])
    max_travel: int = 65
    decoration_density: float = .4
    balance_profile: str = 'standard'
    hero_skills: list = field(default_factory=lambda:[list(s) for s in DEFAULT_HERO_SKILLS])

    @classmethod
    def from_dict(cls, value):
        try:
            fields=dict(value); chapters=[]
            for row in fields.pop('chapters'):
                row=dict(row)
                row['challenge']=Challenge(**row.get('challenge',{}))
                row['reward']=RewardSpec(**row.get('reward',{}))
                row['opportunities']=[Opportunity(**dict(o,reward=RewardSpec(**o.get('reward',{}))))
                                      for o in row.get('opportunities',[])]
                chapters.append(Chapter(**row))
            result=cls(chapters=chapters,**fields)
            result.validate()
            return result
        except (TypeError,KeyError,AttributeError) as exc:
            raise ValueError(f'Invalid scenario specification: {exc}') from exc

    def validate(self):
        if self.balance_profile not in ('standard', 'fixed'):
            raise ValueError('balance_profile: standard or fixed')
        message(self.name,'name',128); message(self.description,'description',3000)
        message(self.hero_name,'hero_name',40); message(self.hero_biography,'hero_biography',1800,True)
        integer(self.seed,-2147483648,2147483647,'seed'); integer(self.max_travel,20,120,'max_travel')
        if type(self.decoration_density) not in (int,float) or not 0<=self.decoration_density<=.65:
            raise ValueError('decoration_density must be 0..0.65')
        stacks(self.army,'starting army',False)
        RewardSpec(spells=self.spells).validate()
        validate_skill_pairs(self.hero_skills)
        if not 2<=len(self.chapters)<=16: raise ValueError('Provide 2..16 chapters')
        ids=[c.id for c in self.chapters]
        if len(set(ids))!=len(ids): raise ValueError('Duplicate chapter id')
        for c in self.chapters:
            if not isinstance(c.id,str) or not re.fullmatch('[a-z][a-z0-9_]{0,31}',c.id):
                raise ValueError('Chapter id must be a short lowercase identifier')
            message(c.title,'chapter.title',80); message(c.text,'chapter.text')
            if c.terrain not in SOILS: raise ValueError(f'Unsupported terrain: {c.terrain}')
            if type(c.optional) is not bool: raise ValueError('optional must be boolean')
            if len(set(c.requires))!=len(c.requires) or len(c.requires)>4:
                raise ValueError('At most four distinct prerequisites')
            if any(k not in ids or k==c.id for k in c.requires): raise ValueError('Invalid prerequisite')
            c.challenge.validate(); c.reward.validate()
            if len(c.opportunities)>2: raise ValueError('At most two side opportunities per chapter')
            stacks(c.sea_battle,'sea_battle')
            if len(c.sea_battle)>1: raise ValueError('One sea monster stack per chapter')
            for o in c.opportunities:
                message(o.title,'opportunity.title',80); message(o.text,'opportunity.text')
                stacks(o.guards,'opportunity.guards'); o.reward.validate()
        roots=[c for c in self.chapters if not c.requires]
        if len(roots)!=1 or roots[0].optional: raise ValueError('Exactly one mandatory starting chapter')
        if roots[0].sea_battle: raise ValueError('Starting chapter cannot have an arrival sea battle')
        if self.finale not in ids: raise ValueError('Missing finale')
        by_id={c.id:c for c in self.chapters}
        ordered=[]; pending=list(self.chapters)
        while pending:
            available=next((c for c in pending if set(c.requires)<=set(ordered)),None)
            if available is None: raise ValueError('Chapter graph has a cycle')
            ordered.append(available.id); pending.remove(available)
        self.order=ordered
        ancestors=set()
        def walk(key):
            if key in ancestors:return
            ancestors.add(key)
            for parent in by_id[key].requires:walk(parent)
        walk(self.finale)
        if any(c.optional for c in self.chapters if c.id in ancestors):
            raise ValueError('Mandatory finale depends on an optional chapter')
        if any(not c.optional and c.id not in ancestors for c in self.chapters):
            raise ValueError('Every mandatory chapter must lead to the finale')
        if any(self.finale in c.requires for c in self.chapters): raise ValueError('Finale must be terminal')

    def to_dict(self):
        return asdict(self)
