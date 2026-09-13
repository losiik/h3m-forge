"""Build a curated offline reference from pinned VCMI and local numeric tables.

No network or map writes. Source descriptions are not redistributed.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

CREATURES = {
    0:('Копейщик','Pikeman'),1:('Алебардщик','Halberdier'),2:('Лучник','Archer'),
    3:('Арбалетчик','Marksman'),6:('Мечник','Swordsman'),7:('Крестоносец','Crusader'),
    10:('Кавалерист','Cavalier'),11:('Чемпион','Champion'),12:('Ангел','Angel'),13:('Архангел','Archangel'),
    92:('Птица рух','Roc'),93:('Громовая птица','Thunderbird'),94:('Циклоп','Cyclops'),
    95:('Король циклопов','Cyclops King'),96:('Чудище','Behemoth'),97:('Древнее чудище','Ancient Behemoth'),
    142:('Кочевник','Nomad'),143:('Вор','Rogue'),
}
ARTIFACTS = {
    7:('Секира кентавра','Centaur Axe'),10:('Дубина огра','Ogre’s Club of Havoc'),
    11:('Меч адского пламени','Sword of Hellfire'),12:('Гладиус титана','Titan’s Gladius'),
    16:('Щит яростного огра','Targ of the Rampaging Ogre'),19:('Шлем белого единорога','Helm of the Alabaster Unicorn'),
    22:('Корона верховного мага','Crown of the Supreme Magi'),28:('Туника короля циклопов','Tunic of the Cyclops King'),
    34:('Щит львиной храбрости','Lion’s Shield of Courage'),101:('Кулон ясновидения','Pendant of Second Sight'),
}
SPELLS = {17:('Молния','Lightning Bolt'),27:('Щит','Shield'),35:('Снятие заклинаний','Dispel'),
          37:('Лечение','Cure'),38:('Воскрешение','Resurrection'),41:('Благословение','Bless'),
          53:('Ускорение','Haste'),54:('Замедление','Slow')}
RESOURCES=('wood','mercury','ore','sulfur','crystal','gems','gold')
STAT_RU={'attack':'Нападение','defence':'Защита','spellpower':'Сила магии','knowledge':'Знания'}
BASE_FACTIONS=('castle','rampart','tower','inferno','necropolis','dungeon','stronghold','fortress','conflux')
# Historical VCMI keys are not always the display name (notably the two golems).
EN_NAMES={32:'Stone Golem',33:'Iron Golem',59:'Zombie',86:'Wolf Rider',87:'Wolf Raider',
          94:'Cyclops',95:'Cyclops King',105:'Dragon Fly',134:'Faerie Dragon'}


def read_jsonc(path):
    # Preserve quoted strings (including URLs) while removing JSON comments.
    pattern=r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/'
    return json.loads(re.sub(pattern,lambda m:m[0] if m[0].startswith('"') else '',path.read_text(encoding='utf-8')))


def build(refs,tables):
    commit=(refs/'vcmi-commit.txt').read_text().strip()
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Pinned VCMI commit required')
    sources=[]
    def source(path,kind):
        sid=path.name
        url=f'https://github.com/vcmi/vcmi/blob/{commit}/'+sid.replace('config_','config/',1).replace('creatures_','creatures/',1).replace('spells_','spells/',1) if kind=='vcmi' else None
        sources.append(dict(id=sid,kind=kind,location=url or 'SuperPack_Rus 1.5/'+sid,
            revision=commit if kind=='vcmi' else 'SuperPack_Rus 1.5; active HotA overrides not inspected',
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),fields='IDs and mechanics' if kind=='vcmi' else 'Numeric reference values and name aliases'))
        return sid
    def table(name,column,minimum):
        p=tables/name;source(p,'local_reference_table')
        rows=csv.reader(p.read_text(encoding='cp1251').splitlines(keepends=True),delimiter='\t')
        return [r for r in rows if len(r)>=minimum and r[column].isdigit()]
    creatures=table('CRTRAITS.txt',8,24);artifacts=table('ARTRAITS.txt',1,23);spells=table('SPTRAITS.txt',2,33)
    if (len(creatures),len(artifacts),len(spells))!=(150,129,81):raise ValueError('Unrecognized reference table layout')
    # Guard against shifted row ordering, independently of selected numeric IDs.
    for rows,idx,name in [(creatures,97,'Древнее Чудище'),(creatures,143,'Вор'),(artifacts,11,'Адский Меч'),(spells,38,'Восстановление')]:
        if rows[idx][0]!=name:raise ValueError('Reference table identity/order mismatch')
    configs={};creature_configs={};spell_configs={}
    for file in sorted(refs.glob('config_*.json')):
        if file.name.startswith(('config_spells_vcmi','config_spells_moats','config_spells_ability')):continue
        sid=source(file,'vcmi');data=read_jsonc(file)
        if file.name=='config_artifacts.json':configs={v['index']:(k,v,sid) for k,v in data.items() if 'index' in v}
        elif 'creatures_' in file.name:creature_configs.update({v['index']:(k,v,sid) for k,v in data.items() if 'index' in v})
        elif 'spells_' in file.name:spell_configs.update({v['index']:(k,v,sid) for k,v in data.items() if 'index' in v})
    def card(category,i,names,key,table_name,sid):
        return dict(category=category,id=i,key=key,name_ru=names[0],name_en=names[1],aliases=[],summary='',tags=[],
            reference_ruleset='heroes3_reference',target_ruleset='hota_1.8.0',
            verification=dict(native_id='verified_against_pinned_reference',properties='reference_only',
                hota_runtime='not_verified',unknown_fields=[]),source_ids=[table_name,sid],
            creature=None,artifact=None,spell=None)
    items=[]
    expected=set(range(145))-{122,124,126,128}
    if set(creature_configs)!=expected:raise ValueError('Expected complete base-game troop IDs; no machines or unused elemental slots')
    for faction in BASE_FACTIONS:
        if sum(v['faction']==faction for _,v,_ in creature_configs.values())!=14:
            raise ValueError(f'Expected 14 troops for {faction}')
    for i in sorted(expected-{138}):  # Halfling has a verified HotA/Factory card in the separate overlay.
        key,d,sid=creature_configs[i]
        names=CREATURES.get(i,(creatures[i][0],EN_NAMES.get(i,re.sub(r'(?<=[a-z])(?=[A-Z])',' ',key).title())))
        key,d,sid=creature_configs[i];r=creatures[i];c=card('creatures',i,names,key,'CRTRAITS.txt',sid)
        if i in (32,33):c['key']='stoneGolem' if i==32 else 'ironGolem'
        c['aliases']=[r[0],r[1]];effects=[]
        for name,v in d.get('abilities',{}).items():
            effects.append(dict(key=name,type=v['type'],subtype=str(v['subtype']) if 'subtype' in v else None,
                value=v.get('val'),scope=v.get('effectRange',v.get('propagator')),value_type=v.get('valueType')))
        if d.get('doubleWide'):
            effects.append(dict(key='two_hexes',type='TWO_HEXES',subtype=None,value=None,scope=None,value_type=None))
        tags=[v['type'].lower() for v in effects]
        if int(r[19]):tags+=['стрелок','ranged']
        if 'flying' in tags:tags+=['летающий']
        if i==13:tags+=['воскрешение','resurrection']
        if i in (96,97):tags+=['снижение защиты']
        c['tags']=tags
        c['summary']=f"{names[0]}: уровень {d['level']}, фракция {d['faction']}."+(' Может воскрешать союзников.' if i==13 else '')
        c['creature']=dict(faction=d['faction'],level=d['level'],attack=int(r[15]),defense=int(r[16]),
            hit_points=int(r[13]),speed=int(r[14]),damage_min=int(r[17]),damage_max=int(r[18]),shots=int(r[19]),
            growth=int(r[11]),cost=dict(zip(RESOURCES,map(int,r[2:9]))),ai_value=int(r[10]),
            fight_value=int(r[9]),horde_growth=int(r[12]),map_amount_min=int(r[21]),map_amount_max=int(r[22]),
            upgrades=[next(j for j,(k,_,_) in creature_configs.items() if k==up) for up in d.get('upgrades',[])],effects=effects)
        c['verification']['unknown_fields']=['creature.effects: selected VCMI fields, not complete HotA combat rules']
        items.append(c)
    for i,names in ARTIFACTS.items():
        key,d,sid=configs[i];r=artifacts[i];c=card('artifacts',i,names,key,'ARTRAITS.txt',sid);c['aliases']=[r[0]]
        effects=[];descriptions=[]
        for name,v in d.get('bonuses',{}).items():
            effects.append(dict(key=name,type=v['type'],subtype=str(v['subtype']) if 'subtype' in v else None,
                value=v.get('val'),scope=v.get('propagator'),value_type=v.get('valueType')))
            if v['type']=='PRIMARY_SKILL':descriptions.append(f"{STAT_RU[v['subtype']]} {v['val']:+d}")
            if v['type']=='SPELL_IMMUNITY' and v['subtype']=='blind':descriptions.append('Защита от ослепления')
        c['summary']='; '.join(descriptions)+'.';c['tags']=[v['type'].lower() for v in effects]+descriptions
        if i==101:c['tags']+=['иммунитет','слепота','blind','ослепление']
        slots=['spell_book','war_machine_4','war_machine_3','war_machine_2','war_machine_1','misc_5','misc_4','misc_3','misc_2','misc_1','feet','left_ring','right_ring','torso','left_hand','right_hand','neck','shoulders','head']
        c['artifact']=dict(slot=[s for s,v in zip(slots,r[2:21]) if v.strip().lower()=='x'],
            cost_gold=int(r[1]),artifact_class={'S':'special','T':'treasure','N':'minor','J':'major','R':'relic'}[r[21]],effects=effects,
            components=None)
        c['verification']['unknown_fields']=['artifact.components']
        items.append(c)
    summaries={17:'Урон молнией.',27:'Снижает урон от рукопашных атак.',35:'Снимает заклинания с отрядов.',
        37:'Восстанавливает здоровье и снимает отрицательные заклинания; погибших не воскрешает.',
        38:'Воскрешает погибших. С продвинутой Магией земли восстановленные воины остаются после боя.',
        41:'Повышает урон отряда.',53:'Увеличивает скорость.',54:'Снижает скорость противника.'}
    for i,names in SPELLS.items():
        key,d,sid=spell_configs[i];r=spells[i];c=card('spells',i,names,key,'SPTRAITS.txt',sid)
        c['aliases']=[r[0]];c['summary']=summaries[i];c['tags']=[key,'боевое']
        levels=[]
        for n,mastery in enumerate(('none','basic','advanced','expert')):
            formula=None;value=None;unit=None;permanent=None
            if i in (17,37,38):formula=f'{r[11]} * spell_power + {r[12+n]}';unit='hit_points'
            elif i==27:value=100-int(r[12+n]);unit='melee_damage_reduction_percent'
            elif i==53:value=int(r[12+n]);unit='speed_bonus'
            elif i==54:value=100-int(r[12+n]);unit='speed_reduction_percent'
            elif i==41:formula='maximum_damage'+(' + 1' if n>=2 else '');unit='damage_per_creature'
            if i==38:permanent=n>=2
            base=d.get('levels',{}).get('base',{});specific=d.get('levels',{}).get(mastery,{})
            mass=specific.get('range',base.get('range'))=='X'
            levels.append(dict(mastery=mastery,mana_cost=int(r[7+n]),mass=mass,formula=formula,value=value,unit=unit,permanent_resurrection=permanent))
        schools=[s for s,v in zip(('earth','water','fire','air'),r[3:7]) if v.strip()=='x']
        c['spell']=dict(level=int(r[2]),schools=schools,target=d.get('targetType','CREATURE').lower(),levels=levels,
            prerequisites=([dict(skill_id=17,minimum_level=2,purpose='Permanent resurrection'),dict(skill_id=7,minimum_level=2,purpose='Learn a level-four spell normally')] if i==38 else []),
            restrictions=['Living creatures only; no undead, mechanical creatures or war machines.'] if i==38 else [],
            counters=list(d.get('counters',{})))
        items.append(c)
    from base_hota_changes import apply_changes
    apply_changes(items,sources,refs)
    return dict(schema_version=1,catalog_version='2026-09-10.3',sources=sources,items=items,
        limitations=['Complete regular base-game troops; artifacts and spells remain a curated selection.',
            'Numeric values come from local reference text tables; active HotA runtime overrides are not verified.',
            'VCMI mechanics are a pinned reference, not proof of identical HotA behavior.',
            'AI value is a reference heuristic, not a combat balance prediction.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--references',type=Path,required=True);p.add_argument('--tables',type=Path,required=True)
    p.add_argument('--output',type=Path,default=Path('src/h3m/data/game_catalog.json'));a=p.parse_args()
    result=build(a.references,a.tables);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(result["items"])} entries: {a.output}')


if __name__=='__main__':main()
