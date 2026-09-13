"""Build complete offline artifact cards from pinned references and native HotA data.

No network, map writes, or execution of source content. Full source prose is not shipped.
"""
import argparse
from collections import Counter
from copy import deepcopy
import csv
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import struct

from build_game_catalog import ARTIFACTS, RESOURCES, STAT_RU, read_jsonc
from build_hota_catalog import documentation

SLOTS=['spell_book','war_machine_4','war_machine_3','war_machine_2','war_machine_1',
       'misc_5','misc_4','misc_3','misc_2','misc_1','feet','left_ring','right_ring',
       'torso','left_hand','right_hand','neck','shoulders','head']
NATIVE_SLOTS={0:[],1:['head'],2:['shoulders'],3:['neck'],4:['right_hand'],5:['left_hand'],
              6:['torso'],7:['left_ring','right_ring'],8:['feet'],
              9:[f'misc_{i}' for i in range(1,6)],10:['war_machine_1'],11:['war_machine_2'],
              12:['war_machine_3'],13:['war_machine_4'],14:['spell_book']}
SETS={129:'Альянс ангелов',130:'Плащ короля нежити',131:'Эликсир жизни',132:'Доспехи проклятого',
      133:'Статуя легиона',134:'Мощь Отца драконов',135:'Грохот титана',136:'Шляпа адмирала',
      137:'Лук снайпера',138:'Колодец волшебника',139:'Кольцо мага',140:'Рог изобилия'}
HOTA={141:'diplomats-cloak',142:'pendant-of-reflection',143:'ironfist-of-the-ogre',146:'cannon',
      147:'trident-of-dominion',148:'shield-of-naval-glory',149:'royal-armor-of-nix',
      150:'crown-of-the-five-seas',151:'wayfarers-boots',152:'runes-of-imminency',153:'demons-horseshoe',
      154:'shamans-puppet',155:'hideous-mask',156:'ring-of-supression',157:'pendant-of-downfall',
      158:'ring-of-oblivion',159:'cape-of-silence',160:'golden-goose',161:'horn-of-the-abyss',
      162:'charm-of-eclipse',163:'seal-of-sunset',164:'plate-of-dying-light',165:'sleepkeeper'}
HOTA_SETS={141:[66,67,68],142:[57,58,59],143:[10,16,28,22],160:[117,116,115]}
HOTA_NOTES={
 141:'Откуп дешевле на 30%; разрешает откуп против нейтралов и отход при защите города. Нейтралы оценивают армию как втрое более сильную.',
 142:'Сопротивление враждебным заклинаниям: суммарно 50% с компонентами.',
 143:'В начале боя накладывает экспертные Ускорение, Жажду крови, Огненный щит и Контрудар на 50 раундов.',
 146:'Боевая машина, занимает место баллисты; атакует отряды и укрепления.',
 147:'Нападение +7.',148:'Защита +7.',149:'Сила магии +6.',150:'Знания +6.',
 151:'Убирает штрафы движения по сложной местности.',152:'Удача врага −1.',153:'Удача врага −1.',
 154:'Удача врага −2.',155:'Боевой дух врага −1.',156:'Боевой дух врага −1.',157:'Боевой дух врага −2.',
 158:'Потери необратимы для обеих сторон: тела исчезают, возвращение погибших и некромантия блокируются; лечение оставшихся возможно.',
 159:'Запрещает магию первого и второго уровней в бою для обеих сторон.',
 160:'Суммарный доход вместе с компонентами: 7000 золота в день.',
 161:'Гибель живого отряда создаёт служащих владельцу фангармов; пределы призыва зависят от здоровья и числа погибших. Фангармы не запускают эффект.',
 162:'Сила магии вражеского героя в бою снижена на 10%.',163:'Сила магии вражеского героя в бою снижена на 10%.',
 164:'Сила магии вражеского героя в бою снижена на 25%.',165:'Защищает армию от магии разума; Сфера уязвимости может снять эту защиту.',
}
SPECIAL_NOTES={0:'Книга хранит изученные героем заклинания.',
 1:'Даёт заклинание, выбранное для конкретного свитка. ID заклинания задаётся в экземпляре предмета.',
 2:'Позволяет возвести уникальное здание Грааля в выбранном городе; эффект зависит от фракции.',
 3:'Осадная машина для разрушения укреплений.',4:'Боевая машина для стрельбы по отрядам; цена HotA 1500 золота.',
 5:'Обеспечивает стрелков боеприпасами, пока тележка не уничтожена.',
 6:'Лечит отряд в бою; эффективность и управление зависят от навыка Первой помощи.'}
EFFECT_RU={'MORALE':'Боевой дух','LUCK':'Удача','STACKS_SPEED':'Скорость войск','STACK_HEALTH':'Здоровье войск',
 'MOVEMENT':'Очки движения','MANA_REGENERATION':'Восстановление маны в день','SPELL_DURATION':'Длительность заклинаний',
 'GENERATE_RESOURCE':'Ресурс в день','CREATURE_GROWTH':'Прирост существ','CREATURE_GROWTH_PERCENT':'Прирост существ, %',
 'SPELL_DAMAGE':'Усиление урона заклинаний','UNDEAD_RAISE_PERCENTAGE':'Бонус некромантии',
 'MAGIC_RESISTANCE':'Сопротивление магии','SURRENDER_DISCOUNT':'Скидка при откупе',
 'SIGHT_RADIUS':'Радиус обзора','SPELL':'Даёт заклинание','SPELLS_OF_SCHOOL':'Заклинания школы',
 'SPELLS_OF_LEVEL':'Заклинания уровня','OPENING_BATTLE_SPELL':'Заклинание в начале боя',
 'SPELL_IMMUNITY':'Иммунитет к заклинанию','BLOCK_ALL_MAGIC':'Запрет магии',
 'BLOCK_MAGIC_ABOVE':'Запрет магии выше уровня','FREE_SHIP_BOARDING':'Посадка и высадка без штрафа',
 'WHIRLPOOL_PROTECTION':'Защита от потерь в водовороте','FLYING_MOVEMENT':'Полёт',
 'WATER_WALKING':'Хождение по воде','FREE_SHOOTING':'Стрельба при блокировке',
 'NO_DISTANCE_PENALTY':'Стрельба без штрафа за дальность','NO_WALL_PENALTY':'Стрельба без штрафа за стену',
 'HP_REGENERATION':'Регенерация здоровья','MANA_PERCENTAGE_REGENERATION':'Восстановление маны, %'}


class Tables(HTMLParser):
    def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        if tag in ('td','th') and self.row is not None:self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(' '.join(self.cell).split()));self.cell=None
        if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None


def native_artifacts(blob):
    def number(p):
        if p<0 or p+4>len(blob):raise ValueError('Truncated artifact record')
        return struct.unpack_from('<I',blob,p)[0]
    def string(p):
        n=number(p)
        if n>20000 or p+4+n>len(blob):raise ValueError('Invalid artifact string')
        return blob[p+4:p+4+n].decode('cp1251'),p+4+n
    result={}
    for m in re.finditer(rb'\x06\x00\x00\x00art[0-9]{3}',blob):
        key,p=string(m.start());i=int(key[3:]);path,p=string(p)
        if path not in ('',f'Artifacts\\art{i}.str'):raise ValueError('Artifact identity mismatch')
        if number(p)!=9 or number(p+4)!=0:raise ValueError('Unknown artifact header')
        p+=8;values=[]
        for _ in range(8):v,p=string(p);values.append(v)
        lines=[line.strip() for line in values[7].splitlines() if line.strip()]
        labels=['cost','slot type','type','disabled as defaults','add new spells','attack bonus','defense bonus','spell power bonus','knowledge bonus']
        if len(lines)!=9:raise ValueError('Unknown artifact config layout')
        nums=[]
        for line,label in zip(lines,labels):
            match=re.fullmatch(r'(-?\d+)\s+#\s+(.+)',line)
            if not match or not match[2].startswith(label):raise ValueError('Unknown artifact config field')
            nums.append(int(match[1]))
        if i in result:raise ValueError('Duplicate artifact ID')
        result[i]=dict(name_ru=values[0],cost=nums[0],slot=NATIVE_SLOTS[nums[1]],
            artifact_class={1:'special',2:'treasure',4:'minor',8:'major',16:'relic'}[nums[2]],primary=nums[5:9])
    if set(result)!=set(HOTA):raise ValueError('Expected native artifact IDs 141..143 and 146..165')
    return result


def effect(key,kind,value=None,subtype=None,scope=None,description=None,**parameters):
    return dict(key=key,type=kind,subtype=subtype,value=value,scope=scope,value_type=None,
                description=description,parameters=parameters)


def convert_effects(d):
    result=[]
    for block in ('bonuses','instanceBonuses'):
        for key,v in d.get(block,{}).items():
            kind=v['type'];sub=str(v['subtype']) if 'subtype' in v else None;value=v.get('val')
            desc=STAT_RU.get(sub,'Характеристика') if kind=='PRIMARY_SKILL' else EFFECT_RU.get(kind,kind)
            if kind!='PRIMARY_SKILL' and sub:desc+=f' ({sub})'
            if value is not None:desc+=f': {value}'
            if kind=='SPELL_IMMUNITY' and sub=='blind':desc='Защита от ослепления'
            result.append(dict(key=key,type=kind,subtype=sub,value=value,
                scope=v.get('effectRange',v.get('propagator')),value_type=v.get('valueType'),description=desc,
                parameters={k:deepcopy(val) for k,val in v.items() if k not in ('type','subtype','val','valueType','propagator','effectRange','description')}))
    return result


def finalize(items):
    by_id={r['id']:r for r in items}
    if len(by_id)!=len(items):raise ValueError('Duplicate artifacts')
    def components(i,seen):
        if i in seen:raise ValueError('Cyclic artifact assembly')
        for child in by_id[i]['artifact']['components']:
            if child not in by_id:raise ValueError('Unknown assembly component')
            yield child
            yield from components(child,seen|{i})
    for row in items:
        a=row['artifact'];inherited=[];slots=Counter()
        for i in components(row['id'],set()):
            child=by_id[i]['artifact']
            row['source_ids']=list(dict.fromkeys(row['source_ids']+by_id[i]['source_ids']))
            for e in child['effects']:
                e=deepcopy(e);e['source_artifact_id']=i;inherited.append(e)
        for i in a['components']:
            choices=by_id[i]['artifact']['slot']
            group='ring' if choices and all('ring' in s for s in choices) else 'misc' if choices and all(s.startswith('misc_') for s in choices) else choices[0] if len(choices)==1 else None
            if group is None:raise ValueError('Ambiguous component slot')
            slots[group]+=1
        a['component_effects']=inherited;a['assembly_slots']=dict(slots);a['effects_include_components']=False
        primary=dict.fromkeys(('attack','defence','spellpower','knowledge'),0);income=dict.fromkeys(RESOURCES,0)
        for e in a['effects']+inherited:
            # Conditional bonuses (e.g. Dragon Blood) must not become hero base stats.
            if e['parameters'].get('limiters'):continue
            if e['type']=='PRIMARY_SKILL':primary[e['subtype']]+=e['value']
            if e['type']=='GENERATE_RESOURCE':income[e['subtype']]+=e['value']
        a.update(effective_primary_skills=primary,effective_daily_income=income)
        if a['components']:
            row['summary']+=' Компоненты: '+', '.join(by_id[i]['name_ru'] for i in a['components'])+'.'
            row['tags']+=['сборный','set','combination']


def build(refs,tables,game_dat):
    config=read_jsonc(refs/'config_artifacts.json')
    base={v['index']:(k,v) for k,v in config.items() if 0<=v.get('index',-1)<=140}
    if set(base)!=set(range(141)):raise ValueError('Incomplete base artifact identities')
    ids={k:i for i,(k,_) in base.items()}
    rows=[r for r in csv.reader((tables/'ARTRAITS.txt').read_text(encoding='cp1251').splitlines(keepends=True),delimiter='\t') if len(r)>=23 and r[1].isdigit()]
    if len(rows)!=129 or rows[11][0]!='Адский Меч':raise ValueError('Unknown ARTRAITS layout')
    native=native_artifacts(game_dat.read_bytes())
    sections=documentation((refs/'hota-documentation-en.html').read_text(encoding='utf-8'))
    changes=(refs/'hota-changelog-en.txt').read_text(encoding='utf-8-sig')
    if '5/10/15/30% Necromancy boost values are back' not in changes:raise ValueError('Missing 1.8 necromancy restoration')
    sources=[]
    def source(sid,path,kind,url,revision,fields):
        sources.append(dict(id=sid,kind=kind,location=url,revision=revision,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),fields=fields))
    commit=(refs/'vcmi-commit.txt').read_text().strip()
    if not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('Unpinned source')
    source('art-vcmi',refs/'config_artifacts.json','vcmi',f'https://github.com/vcmi/vcmi/blob/{commit}/config/artifacts.json',commit,'IDs, components, bonus and instanceBonus structures, assembly values')
    source('art-table',tables/'ARTRAITS.txt','local_reference_table','SuperPack_Rus 1.5/ARTRAITS.txt','Reference table','Base names, prices, slots and classes')
    source('art-native',game_dat,'local_game_data','HotA.dat','Local 1.8.0 snapshot','New artifact IDs, names, slots, classes, ordinary prices and primary bonuses; set price zero is a placeholder')
    source('art-docs',refs/'hota-documentation-en.html','official_documentation','https://h3hota.com/en/documentation','Retrieved 2026-09-10','HotA effects, component lists, set prices, slot occupancy and restrictions')
    source('art-changelog',refs/'hota-changelog-en.txt','official_changelog','https://download.h3hota.com/upd/changelogs/eng.txt','Through 1.8.1; retrieved 2026-09-10','Necromancy bonuses restored in 1.8.0')
    article=Tables();article.feed((refs/'pro-onlineigry-artifacts.html').read_text(encoding='utf-8'))
    parsed=[r for r in article.rows if len(r)==6 and r[3] in ('S','T','N','J','R') and r[4].isdigit()]
    if len(parsed)<120:raise ValueError('Incomplete article tables')
    source('art-user-page',refs/'pro-onlineigry-artifacts.html','community_reference','https://pro-onlineigry.ru/homm3/artefakty-i-sety','Retrieved 2026-09-10; article dated 2024-09-22','Matched name/price cross-checks only; not authoritative HotA mechanics')
    def card(i,key,ru,en,slots,cost,cls,fx,parts,source_ids,verified=False):
        return dict(category='artifacts',id=i,key=key,name_ru=ru,name_en=en,aliases=[],
            summary='; '.join(e['description'] for e in fx if e.get('description')) or ru+'.',
            tags=list(dict.fromkeys(e['type'].lower() for e in fx)),reference_ruleset='hota_1.8.0' if verified else 'heroes3_reference',
            target_ruleset='hota_1.8.0',verification=dict(native_id='verified_against_pinned_reference',
            properties='official_documentation_and_native_data' if verified else 'reference_only',hota_runtime='not_verified',
            unknown_fields=['artifact.effects: documented/reference mechanics; not a complete executable combat model']),
            source_ids=source_ids,version_notes=[],artifact=dict(slot=slots,cost_gold=cost,artifact_class=cls,
            effects=fx,components=parts,default_availability='not_verified'),creature=None,spell=None)
    items=[]
    for i,(key,d) in sorted(base.items()):
        ru,en=ARTIFACTS.get(i,(rows[i][0] if i<129 else SETS[i],re.sub(r'(?<=[a-z])(?=[A-Z])',' ',key).title()))
        slots=[s for s,v in zip(SLOTS,rows[i][2:21]) if v.strip().lower()=='x'] if i<129 else []
        cost=int(rows[i][1]) if i<129 else d['value']
        cls={'S':'special','T':'treasure','N':'minor','J':'major','R':'relic'}[rows[i][21]] if i<129 else 'combination'
        row=card(i,key,ru,en,slots,cost,cls,convert_effects(d),[ids[k] for k in d.get('components',[])],['art-vcmi','art-table'])
        if i in SPECIAL_NOTES:row['artifact']['effects'].append(effect('special_item','DOCUMENTED_ABILITY',description=SPECIAL_NOTES[i]))
        if i<129:row['aliases']=[rows[i][0]]
        if i>=129:row['verification']['unknown_fields']+=['artifact.slot: base combination anchor not verified; see assembly_slots for required occupied slots']
        if i in (4,70,98):
            general=sections['general-gameplay/creatures'] if i==4 else sections['general-gameplay/artifacts']
            needle={4:'Ballista price reduced from 2500 to 1500.',70:'reduced from 300 to 200',98:'reduced from 600 to 400'}[i]
            if needle not in general:raise ValueError('Missing HotA price/movement change')
            if i==4:row['artifact']['cost_gold']=1500
            else:
                fx=next(e for e in row['artifact']['effects'] if e['type']=='MOVEMENT')
                fx['value']={70:200,98:400}[i];fx['description']=f"Очки движения по суше: +{fx['value']}"
            row['version_notes']=['Применена поправка цены или движения HotA.']
            row['verification']['properties']='reference_with_documented_hota_changes';row['source_ids']+=['art-docs']
        if i in (54,55,56,130):
            row['source_ids']+=['art-changelog'];row['version_notes']+=['В 1.8.0 восстановлены бонусы некромантии компонентов 5/10/15%, суммарно 30%.']
        if i in (57,58,59,83,126):row['artifact']['default_availability']='disabled_by_default'
        if i==130:row['artifact']['default_availability']='assembly_disabled_by_default'
        if i==125:row['version_notes']+=['В HotA Оковы войны работают только в бою двух героев.']
        if i in (57,58,59,83,125,126,130):row['source_ids']+=['art-docs']
        if i==125:
            for e in row['artifact']['effects']:e['parameters']['requires_heroes_on_both_sides']=True
        if i==101:row['tags']+=['иммунитет','слепота','blind','ослепление']
        row['summary']='; '.join(e['description'] for e in row['artifact']['effects'] if e.get('description')) or ru+'.'
        items.append(row)
    for i,key in HOTA.items():
        n=native[i];parts=HOTA_SETS.get(i,[]);fx=[]
        section='cove/cannon' if i==146 else 'new-artifacts/'+('not-for-random-maps/' if i in (142,161,165) else '')+key
        text=sections[section]
        expected_primary={147:[7,0,0,0],148:[0,7,0,0],149:[0,0,6,0],150:[0,0,0,6]}.get(i,[0,0,0,0])
        if n['primary']!=expected_primary:raise ValueError('Unexpected native primary bonus; audit official documentation')
        if i==146:
            if '3000' not in text:raise ValueError('Cannon price source changed')
            cost=n['cost'];en='Cannon'
        else:
            match=re.search(r'Cost:\s*(\d+)',text)
            if not match:raise ValueError('Missing official artifact price')
            cost=int(match[1]);en=text.split(' Class:',1)[0]
            cls=re.search(r'Class:\s*(\w+)',text)[1].lower()
            if cls!=n['artifact_class']:raise ValueError('Artifact class mismatch')
            if (not parts and cost!=n['cost']) or (parts and n['cost']!=0):raise ValueError('Artifact cost mismatch')
            position=re.search(r'(?:Carried in|Worn on|Worn in) (?:the )?(right hand|left hand|body|head|foot|finger|shoulders|neck|“Other” slot)',text)
            if not position:raise ValueError('Missing official artifact slot')
            slot_number={'right hand':4,'left hand':5,'body':6,'head':1,'foot':8,'finger':7,'shoulders':2,'neck':3,'“Other” slot':9}[position[1]]
            if n['slot']!=NATIVE_SLOTS[slot_number]:raise ValueError('Native/documentation slot mismatch')
        for stat,val in zip(('attack','defence','spellpower','knowledge'),n['primary']):
            if val:fx.append(effect(stat,'PRIMARY_SKILL',val,stat,description=f'{STAT_RU[stat]} +{val}'))
        if i in (152,153,154):fx.append(effect('enemy_luck','LUCK',-2 if i==154 else -1,scope='enemy_army'))
        if i in (155,156,157):fx.append(effect('enemy_morale','MORALE',-2 if i==157 else -1,scope='enemy_army'))
        if i in (162,163,164):fx.append(effect('interference','ENEMY_SPELL_POWER_REDUCTION_PERCENT',25 if i==164 else 10,scope='enemy_hero'))
        if i==160:fx.append(effect('gold','GENERATE_RESOURCE',4750,'gold',scope='owner_per_day'))
        if i==142:fx.append(effect('resistance','MAGIC_RESISTANCE',20,scope='own_army'))
        fx.append(effect('hota_notes','DOCUMENTED_ABILITY',description=HOTA_NOTES[i]))
        row=card(i,key,n['name_ru'],en,n['slot'],cost,n['artifact_class'],fx,parts,['art-native','art-docs'],True)
        if i in (142,161,165):row['artifact']['default_availability']='disabled_on_random_maps_by_default'
        if parts:row['version_notes']=['Свойства компонентов учитываются отдельно; цена набора взята из документации, а не из нулевого поля HotA.dat.']
        items.append(row)
    for row in items:
        cls=row['artifact']['artifact_class']
        row['tags']+=[cls,{'special':'специальный','treasure':'сокровище','minor':'малый',
            'major':'великий','relic':'реликвия','combination':'сборный'}[cls]]
        if row['id']==158:row['tags']+=['воскрешение','resurrection','запрет воскрешения']
        if row['id']==165:row['tags']+=['иммунитет','магия разума']
    # Only exact name matches enrich provenance. The article is never an ID source.
    norm=lambda s:re.sub(r'[^\w]','',s.casefold().replace('ё','е'))
    matched=0
    for row in items:
        names={norm(n) for n in [row['name_ru'],*row['aliases']]}
        found=[r for r in parsed if norm(r[0]) in names]
        if len(found)>1:raise ValueError('Ambiguous article artifact name')
        if found:
            r=found[0];row['source_ids'].append('art-user-page');matched+=1
            if int(r[4])!=row['artifact']['cost_gold']:
                row['version_notes'].append(f"В предложенной статье цена {r[4]}; каталог использует {row['artifact']['cost_gold']} по основному источнику.")
    finalize(items)
    return dict(schema_version=1,catalog_version='2026-09-10.4',sources=sources,items=items,
        article_matched_cards=matched,limitations=[
        '164 artifact identities: base 0..140 plus HotA 141..143 and 146..165. Reserved 144/145 excluded.',
        'Base stats/mechanics use pinned references with documented HotA changes; runtime and all interaction rules are not verified.',
        'Combination effects exclude components. component_effects and effective totals avoid double counting; assembly_slots describe occupied groups.',
        'Base combination anchor slots are unverified (slot=[]); combination is a display category, not a certified native rarity.',
        'cost_gold is a reference value, not a guaranteed shop buy/sell price. Map availability can override defaults.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('references','tables','game-dat'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--output',type=Path,default=Path('src/h3m/data/artifact_catalog.json'))
    a=p.parse_args();data=build(a.references,a.tables,a.game_dat)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(data["items"])} artifacts; {data["article_matched_cards"]} article matches; {a.output}')


if __name__=='__main__':main()
