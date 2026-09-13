"""Compile offline HotA creature profiles from explicit local source snapshots.

Reads data only. Does not download pages, execute game code or modify maps.
Rejects unknown binary layouts and numeric disagreements instead of guessing.
"""
import argparse
from copy import deepcopy
import csv
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import struct

RESOURCES = ('wood', 'mercury', 'ore', 'sulfur', 'crystal', 'gems', 'gold')
GROUPS = {
    'cove': [(153,'nymph'),(154,'oceanid'),(155,'crew-mate'),(156,'seaman'),
             (157,'pirate'),(158,'corsair'),(151,'sea-dog'),(159,'stormbird'),
             (160,'ayssid'),(161,'sea-witch'),(162,'sorceress'),(163,'nix'),
             (164,'nix-warrior'),(165,'sea-serpent'),(166,'haspid')],
    'factory': [(138,'halfling'),(171,'halfling-grenadier'),(172,'mechanic'),
                (173,'engineer'),(174,'armadillo'),(175,'bellwether-armadillo'),
                (176,'automaton'),(177,'sentinel-automaton'),(178,'sandworm'),
                (179,'olgoi-khorkhoi'),(180,'gunslinger'),(181,'bounty-hunter'),
                (182,'couatl'),(183,'crimson-couatl'),(184,'dreadnought'),(185,'juggernaut')],
    'bulwark': list(zip(range(186,200), ('kobold','kobold-foreman','mountain-ram',
        'argali','snow-elf','steel-elf','yeti','yeti-runemaster','shaman','great-shaman',
        'mammoth','war-mammoth','jotunn','jotunn-warlord'))),
    'neutral': [(167,'satyr'),(168,'fangarm'),(169,'leprechaun'),(170,'steel-golem')],
}
UPGRADES = {138:[171],153:[154],155:[156],157:[158],158:[151],159:[160],
            161:[162],163:[164],165:[166],172:[173],174:[175],176:[177],
            178:[179],180:[181],182:[183],184:[185],
            **{i:[i+1] for i in range(186,200,2)}}

# Original concise descriptions. Detailed damage formulas remain explicitly incomplete.
NOTES = {
 138:'Удача всегда положительная.',171:'Положительная удача; при стрельбе игнорирует 20% защиты цели.',
 153:'Телепортируется; невосприимчива к Ледяной молнии и Кольцу холода.',
 154:'Телепортируется; невосприимчива к Ледяной молнии и Кольцу холода.',
 155:'Пехота без особых боевых способностей.',156:'Улучшенная пехота без особых боевых способностей.',
 157:'Стреляет; в рукопашной нет штрафа к урону.',
 158:'Нет штрафа за рукопашную атаку и ответного удара.',
 151:'Без штрафа в рукопашной и ответного удара; точный выстрел может дополнительно убивать существ.',
 159:'Летающее существо, занимает две клетки.',160:'Летает; после убийства существа атакует ещё раз.',
 161:'Выстрел накладывает Слабость, а если она уже есть — Разрушающий луч; базовая магия.',
 162:'Выстрел накладывает Слабость, а если она уже есть — Разрушающий луч; продвинутая магия.',
 163:'При атаке на никса игнорируется 30% нападения противника.',
 164:'При атаке на никса-воина игнорируется 60% нападения противника.',
 165:'Атака может отравить цель и уменьшить её максимальное здоровье.',
 166:'Отравляет; потери здоровья собственного отряда усиливают его урон.',
 167:'Трижды за бой применяет продвинутую Радость на шесть раундов.',
 168:'Летает, невосприимчив к магии разума, отвечает без ограничений; может гипнотизировать атакованную цель.',
 169:'Удваивает шанс удачи союзников; трижды за бой применяет продвинутую Удачу на шесть раундов.',
 170:'Голем; получает на 80% меньше урона от заклинаний.',
 172:'Сквозная атака; один ремонт за бой восстанавливает по 10 здоровья на механика, включая погибшие механизмы.',
 173:'Сквозная атака; один ремонт за бой восстанавливает по 20 здоровья на инженера, включая погибшие механизмы.',
 174:'Занимает две клетки.',175:'Занимает две клетки; быстрее обычного броненосца.',
 176:'Механизм: ремонтируется, не воскрешается магией; можно включить подрыв отряда при гибели.',
 177:'Механизм с подрывом при гибели и атакой без ответа; доступен ремонт вместо Воскрешения.',
 178:'Подземное перемещение не работает на корабле и Волшебных облаках; иммунитет к ослеплению и окаменению.',
 179:'Подземное перемещение и иммунитеты червя; съеденные тела дают дополнительные удары.',
 180:'Один упреждающий выстрел за раунд; не действует при блокировке стрельбы, против машин и площадных стрелков.',
 181:'Упреждающие выстрелы без лимита за раунд; ограничения целей и блокировки стрельбы сохраняются.',
 182:'Один раз за бой пропускает действие ради неуязвимости до своего следующего хода.',
 183:'Один раз за бой получает неуязвимость без пропуска действия; она снимается на следующем обычном ходу.',
 184:'Ремонтируемый механизм; тепловой удар вместо движения поражает область, включая союзников, без ответа.',
 185:'Усиленный ремонтируемый механизм; тепловой удар поражает область, включая союзников, без ответа.',
 186:'Каждый кобольд приносит владельцу одно золото в день.',187:'Каждый кобольд-старшина приносит владельцу одно золото в день.',
 188:'Занимает две клетки.',189:'Невосприимчив к ледяным заклинаниям; соседние враги получают на 20% больше урона от магии.',
 190:'Стрелок без штрафа за рукопашную атаку.',191:'Стреляет даже при блокировке; соседние цели атакует только врукопашную, без штрафа.',
 192:'Отрицательные эффекты с конечной длительностью действуют только один раунд.',
 193:'Сокращает отрицательные эффекты до раунда; накапливает до девяти уровней рун с бонусами экспертного навыка.',
 194:'Трижды за бой накладывает продвинутый Воздушный щит на шесть раундов.',
 195:'Воздушный щит трижды за бой; выстрел с вероятностью 20% замораживает на три раунда до получения урона.',
 196:'Выносливое существо, занимает две клетки.',197:'Действие «Защита» повышает защиту на 100% вместо обычных 20%.',
 198:'Один экспертный Телепорт союзника за бой; скорость вражеских летающих существ снижена на один.',
 199:'Экспертный Телепорт союзников без лимита за бой; скорость вражеских летающих существ снижена на два.',
}


class Sections(HTMLParser):
    def __init__(self):
        super().__init__(); self.key=None; self.rows={}

    def handle_starttag(self, tag, attrs):
        if re.fullmatch(r'h[1-6]',tag):
            self.key=dict(attrs).get('id')
            if self.key:
                if self.key in self.rows:raise ValueError(f'Duplicate documentation section: {self.key}')
                self.rows[self.key]=[]

    def handle_data(self, data):
        if self.key:self.rows[self.key].append(data)


def documentation(html):
    parser=Sections(); parser.feed(html)
    return {key:re.sub(r'\s+',' ',' '.join(parts)).strip() for key,parts in parser.rows.items()}


def numeric(text):
    def number(label):
        match=re.search(label+r'\s*:?\s*(\d+)',text)
        if not match:raise ValueError(f'Missing numeric field: {label}')
        return int(match[1])
    def interval(label):
        match=re.search(label+r':\s*(\d+)(?:\s*[–−-]\s*(\d+))?',text)
        if not match:raise ValueError(f'Missing interval: {label}')
        return int(match[1]),int(match[2] or match[1])
    cost_match=re.search(r'Cost:\s*([^.]+)\.',text)
    if not cost_match:raise ValueError('Missing cost')
    parts=re.findall(r'(\d+)\s+(gold|wood|mercury|ore|sulfur|crystals?|gems?)',cost_match[1])
    residue=re.sub(r'\d+\s+(gold|wood|mercury|ore|sulfur|crystals?|gems?)','',cost_match[1])
    if not parts or residue.strip(' ,+'):raise ValueError('Unrecognized cost')
    cost=dict.fromkeys(RESOURCES,0)
    for value,key in parts:
        cost[{'crystals':'crystal','gem':'gems'}.get(key,key)]=int(value)
    lo,hi=interval('Damage'); amin,amax=interval('Amount on map')
    return dict(level=number(r'\bLevel'),attack=number('Attack:'),defense=number('Defense:'),
        hit_points=number('Health:'),speed=number('Speed:'),damage_min=lo,damage_max=hi,
        shots=number('Shots:'),growth=number(r'Population growth(?:\s*\([^)]*\))?:'),
        horde_growth=int(m[1]) if (m:=re.search(r'Population growth[^:]*:\s*\d+\s*\(\+(\d+)\)',text)) else 0,
        cost=cost,ai_value=number('AI Value:'),fight_value=number('Fight Value:'),
        map_amount_min=amin,map_amount_max=amax)


def native_creatures(blob):
    rows={}
    def u32(p):
        if p<0 or p+4>len(blob):raise ValueError('Truncated HotA.dat')
        return struct.unpack_from('<I',blob,p)[0]
    def string(p):
        n=u32(p); end=p+4+n
        if n>4096 or end>len(blob):raise ValueError('Invalid HotA.dat string')
        return blob[p+4:end].decode('cp1251'),end
    for match in re.finditer(rb'monst([0-9]{3})(?![0-9])',blob):
        i=int(match[1]); name,p=string(match.start()-4); path,p=string(p)
        if name!=f'monst{i}' or path!=f'Monsters\\monster{i}.str':raise ValueError('Creature identity mismatch')
        if u32(p)!=9 or u32(p+4)!=0:raise ValueError('Unknown creature record header')
        p+=8; abbreviation,p=string(p); sprite,p=string(p); ru,p=string(p); plural,p=string(p)
        if blob[p:p+17]!=bytes(16)+b'\x01' or u32(p+17)!=116:raise ValueError('Unknown creature stat layout')
        if p+137>len(blob):raise ValueError('Truncated creature stats')
        a=struct.unpack_from('<29I',blob,p+21)
        if i in rows:raise ValueError('Duplicate native creature ID')
        rows[i]=dict(name_ru=ru,plural=plural,faction_id=a[0],sprite=sprite,
            stats=dict(level=a[1]+1,attack=a[21],defense=a[22],hit_points=a[19],speed=a[20],
            damage_min=a[23],damage_max=a[24],shots=a[25],growth=a[17],horde_growth=a[18],
            cost=dict(zip(RESOURCES,a[8:15])),ai_value=a[16],fight_value=a[15],map_amount_min=a[27],map_amount_max=a[28]))
    if set(rows)!=set(range(150,200)):raise ValueError('Expected 50 native records (150..199)')
    return rows


def effects(text, i):
    result=[]
    for needle,kind in [('Shooter.','SHOOTER'),('Flight.','FLYING'),('Takes 2 hexes.','TWO_HEXES'),
                        ('Teleportation.','TELEPORTING'),('Mechanical creature.','MECHANICAL'),
                        ('No melee penalty.','NO_MELEE_PENALTY'),('No enemy retaliation','NO_RETALIATION'),
                        ('Mind spell immunity.','MIND_IMMUNITY')]:
        if needle.casefold() in text.casefold():
            result.append(dict(key=kind.lower(),type=kind,subtype=None,value=None,scope=None,value_type=None))
    result.append(dict(key='hota_ability_notes',type='DOCUMENTED_ABILITY',subtype=None,value=None,
        scope=None,value_type=None,description=NOTES[i]))
    return result


def build(refs, game_dat, tables):
    html=(refs/'hota-documentation-en.html').read_text(encoding='utf-8')
    sections=documentation(html); native=native_creatures(game_dat.read_bytes())
    changelog=(refs/'hota-changelog-en.txt').read_text(encoding='utf-8-sig')
    if not re.search(r'Version 1\.8\.1 \(25\.08\.2026\)',changelog):raise ValueError('Missing 1.8.1 changelog')
    if 'War Mammoths: Fight Value and AI Value 1601 -> 1672' not in changelog:raise ValueError('Unrecognized Mammoth change')
    rows=[r for r in csv.reader((tables/'CRTRAITS.txt').read_text(encoding='cp1251').splitlines(keepends=True),delimiter='\t') if len(r)>=24 and r[8].isdigit()]
    if len(rows)!=150 or rows[138][0]!='Хоббит':raise ValueError('Unknown Halfling reference row')
    # Base-game native identity is independently pinned in the VCMI reference.
    from build_game_catalog import read_jsonc
    vcmi=read_jsonc(refs/'config_creatures_neutral.json')
    if vcmi['halfling']['index']!=138:raise ValueError('Halfling ID mismatch')
    r=rows[138]
    native[138]=dict(name_ru='Полурослик',plural=r[1],faction_id=10,stats=dict(level=1,
        attack=int(r[15]),defense=int(r[16]),hit_points=int(r[13]),speed=int(r[14]),
        damage_min=int(r[17]),damage_max=int(r[18]),shots=int(r[19]),growth=int(r[11]),
        horde_growth=int(r[12]),cost=dict(zip(RESOURCES,map(int,r[2:9]))),ai_value=int(r[10]),
        fight_value=int(r[9]),map_amount_min=int(r[21]),map_amount_max=int(r[22])))
    sources=[]
    def source(sid,path,kind,location,revision,fields):
        sources.append(dict(id=sid,kind=kind,location=location,revision=revision,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),fields=fields))
    source('hota-dat-1.8.0',game_dat,'local_game_data','HotA.dat','HotA 1.8.0 data snapshot',
        'Native IDs 150..199, RU aliases, faction and numeric base stats; no DLL execution')
    source('hota-docs-20260910',refs/'hota-documentation-en.html','official_documentation',
        'https://h3hota.com/en/documentation','Retrieved 2026-09-10; numeric rules 1.8.1',
        'Creature stats, upgrades, factions, concise ability summaries')
    source('hota-changes-1.8.1',refs/'hota-changelog-en.txt','official_changelog',
        'https://download.h3hota.com/upd/changelogs/eng.txt','1.8.1 released 2026-08-25; retrieved 2026-09-10',
        '1.8.0 -> 1.8.1 delta: War Mammoth AI/Fight 1601 -> 1672; behavior bug fixes')
    commit=(refs/'vcmi-commit.txt').read_text().strip()
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Unpinned VCMI identity source')
    source('hota-halfling-id',refs/'config_creatures_neutral.json','vcmi',
        f'https://github.com/vcmi/vcmi/blob/{commit}/config/creatures/neutral.json',commit,'Native Halfling ID 138')
    source('hota-halfling-table',tables/'CRTRAITS.txt','local_reference_table',
        'SuperPack_Rus 1.5/CRTRAITS.txt','Base table cross-checked with HotA documentation','Halfling numeric reference')
    items=[]
    for faction,entries in GROUPS.items():
        for i,key in entries:
            section=f'{faction}/units/{key}' if faction!='neutral' else f'new-neutral-creatures/{key}'
            text=sections[section]; stats=numeric(text); expected=deepcopy(native[i]['stats'])
            if i==197:
                if (expected['ai_value'],expected['fight_value'])!=(1601,1601):raise ValueError('Expected HotA 1.8.0 Mammoth baseline')
                expected.update(ai_value=1672,fight_value=1672)
            if stats!=expected:
                diff={k:(expected[k],stats[k]) for k in stats if stats[k]!=expected[k]}
                raise ValueError(f'{i} {key}: native/documentation mismatch: {diff}')
            if native[i]['faction_id']!={'cove':9,'factory':10,'bulwark':11,'neutral':0xffffffff}[faction]:raise ValueError('Faction mismatch')
            stats.update(faction=faction,upgrades=UPGRADES.get(i,[]),effects=effects(text,i))
            tags=['hota',faction]+[e['type'].lower() for e in stats['effects'] if e['type']!='DOCUMENTED_ABILITY']
            if stats['shots']:tags+=['ranged','стрелок']
            if any(e['type']=='MECHANICAL' for e in stats['effects']):tags+=['ремонт','механизм']
            name_ru=native[i]['name_ru']
            items.append(dict(category='creatures',id=i,key=key,name_ru=name_ru,
                name_en=text.split(' Level',1)[0],aliases=[native[i]['plural']],summary=NOTES[i],tags=tags,
                reference_ruleset='hota_1.8.1',target_ruleset='hota_1.8.1',
                verification=dict(native_id='verified_against_pinned_reference',
                    properties='official_documentation_and_native_data',hota_runtime='not_verified',
                    unknown_fields=['creature.effects: concise mechanics; not a complete executable combat model']),
                source_ids=['hota-docs-20260910','hota-changes-1.8.1']+(['hota-halfling-id','hota-halfling-table'] if i==138 else ['hota-dat-1.8.0']),
                version_notes=[],creature=stats,artifact=None,spell=None))
    profiles={}
    for ruleset in ('hota_1.8.0','hota_1.8.1'):
        selected=deepcopy(items)
        for item in selected:
            item.update(reference_ruleset=ruleset,target_ruleset=ruleset)
            if item['id']==197:
                value=1601 if ruleset=='hota_1.8.0' else 1672
                item['creature'].update(ai_value=value,fight_value=value)
                item['version_notes']=['1.8.1: AI/Fight Value 1672 вместо 1601; стандартная награда Пандоры 12 вместо 15. Это не состав авторского ящика.']
            if item['id'] in (186,187):item['version_notes']=['1.8.1 исправляет выдачу золота кобольдами в шахтах и гарнизонах чужим игрокам.']
            if item['id']==193:item['version_notes']=['1.8.1 исправляет накопление рун сверх предела после гибели и воскрешения.']
            if item['id'] in (198,199):item['version_notes']=['1.8.1 исправляет решения ИИ при применении Телепорта.']
        profiles[ruleset]=selected
    return dict(schema_version=1,catalog_version='2026-09-10.3',sources=sources,profiles=profiles,
        limitations=['HotA snapshot verified against official documentation and native 1.8.0 data, with explicit 1.8.1 changelog delta; not a live runtime inspection.',
            'Includes all Cove, Factory and Bulwark troops and four new neutral creatures. Cannon 150 and technical Electric Tower 152 are excluded.',
            'Base-game cards use pinned reference tables with selected documented HotA corrections; other mods and future releases are not covered.',
            'Ability summaries are incomplete combat rules; AI/Fight values do not certify encounter difficulty.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--references',type=Path,required=True)
    p.add_argument('--game-dat',type=Path,required=True)
    p.add_argument('--tables',type=Path,required=True)
    p.add_argument('--output',type=Path,default=Path('src/h3m/data/hota_creatures.json'))
    a=p.parse_args(); result=build(a.references,a.game_dat,a.tables)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(result["profiles"]["hota_1.8.1"])} creatures, two profiles: {a.output}')


if __name__=='__main__':main()
