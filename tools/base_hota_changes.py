"""Explicit documented HotA deltas over the original creature reference.

Unspecified AI values are null, never a silently retained original value.
The remaining reference fields are NOT certified as active runtime values.
"""
import hashlib


def apply_changes(items,sources,refs):
    from build_hota_catalog import documentation
    doc=refs/'hota-documentation-en.html'
    change=refs/'hota-changelog-en.txt'
    sections=documentation(doc.read_text(encoding='utf-8'))
    text=change.read_text(encoding='utf-8-sig')
    general=sections['general-gameplay/creatures']
    conflux=sections['town-gameplay/conflux']
    inferno=sections['town-gameplay/inferno']
    for phrase,section in [
        ('Cost of Psychic Elementals increased from 750 to 950 gold.',conflux),
        ('Cost of Magic Elementals increased from 800 to 1200 gold.',conflux),
        ('Cost of Firebirds increased from 1500 to 2000.',conflux),
        ('3000 gold + 1 mercury',conflux),
        ('Growth of Firebirds and Phoenixes decreased to 1',conflux),
        ('Fire immunity of Firebirds replaced with 50% Fire Resist.',general),
        ('Arch Devil decreases Luck by 2',inferno),
        ('Default map count of Sharpshooters increased to 10–16',general),
        ('Lizardmen: Fight Value: 115 -> 137, AI Value: 126 -> 151',text),
        ('Lizard Warriors: Fight Value: 130 -> 174, AI Value: 156 -> 209',text),
        ('AI Value for Efreet Sultans has been increased from 1848 to 2343, and their Fight Value, from 1584 to 1802',text),
    ]:
        if phrase not in section:raise ValueError(f'Changed/missing official HotA evidence: {phrase}')
    sources.extend([
        dict(id='base-hota-docs',kind='official_documentation',location='https://h3hota.com/en/documentation',
             revision='Retrieved 2026-09-10; base creature changes for HotA 1.8.0/1.8.1',
             sha256=hashlib.sha256(doc.read_bytes()).hexdigest(),fields='Documented original creature changes; incomplete runtime verification'),
        dict(id='base-hota-changelog',kind='official_changelog',location='https://download.h3hota.com/upd/changelogs/eng.txt',
             revision='Retrieved 2026-09-10; through 1.8.1',sha256=hashlib.sha256(change.read_bytes()).hexdigest(),
             fields='Explicit AI/Fight deltas and Cyclops wall-attack fix')])
    unknown_ai={8:'Monk',38:'Naga',69:'Ghost Dragon',81:'Scorpicore',82:'Red Dragon',
                95:'Cyclops King',130:'Firebird',134:'Fairy Dragon'}
    for name in unknown_ai.values():
        if name not in general:raise ValueError(f'Missing AI change evidence: {name}')
    for row in items:
        if row['category']!='creatures':continue
        i=row['id'];c=row['creature'];notes=[]
        if i in unknown_ai:
            c['ai_value']=None
            row['verification']['unknown_fields'].append('creature.ai_value: HotA changes documented without exact current number')
            notes.append('HotA меняет AI value; точное актуальное число в использованном источнике не приведено.')
        if i in (100,101,53):
            ai,fight={100:(151,137),101:(209,174),53:(2343,1802)}[i]
            c.update(ai_value=ai,fight_value=fight)
            notes.append(f'По журналу HotA: AI value {ai}, Fight value {fight}.')
        if i in (120,121,130,131):
            gold={120:950,121:1200,130:2000,131:3000}[i]
            c['cost']['gold']=gold
            notes.append(f'Цена HotA: {gold} золота'+(' и 1 ртуть.' if i==131 else '.'))
        if i in (130,131):
            c.update(growth=1,horde_growth=1)
            notes.append('Базовый прирост 1; Хранилище праха добавляет 1. Модификатор замка учитывается отдельно.')
        if i==130:
            old=[e for e in c['effects'] if e['type']=='SPELL_SCHOOL_IMMUNITY' and e['subtype']=='fire']
            if len(old)!=1:raise ValueError('Expected original Firebird immunity')
            c['effects'].remove(old[0])
            c['effects'].append(dict(key='hota_fire_resistance',type='SPELL_DAMAGE_REDUCTION',subtype='fire',
                value=50,scope='self',value_type='percent',description='На 50% меньше урона от заклинаний огня; это не полный иммунитет.'))
            notes.append('Иммунитет к огню заменён снижением урона от огненных заклинаний на 50%.')
        if i==55:
            luck=[e for e in c['effects'] if e['type']=='LUCK']
            if len(luck)!=1 or luck[0]['value']!=-1:raise ValueError('Expected original Arch Devil luck effect')
            luck[0].update(value=-2,scope='enemy_army')
            notes.append('Архидьявол снижает удачу противника на 2.')
        if i==137:
            c.update(map_amount_min=10,map_amount_max=16)
            notes.append('Типовая численность снайперов на случайной карте: 10–16.')
        if i in (45,64,65):
            notes.append('HotA разрешает прицельный выстрел по клетке поля боя; ограничения соседних клеток сохраняются без Лука снайпера.')
        if i in (94,95):
            notes.append('1.8.1: циклопы не могут атаковать стены после исчерпания выстрелов.')
        if notes:
            row['source_ids']+=['base-hota-docs','base-hota-changelog']
            row['verification']['properties']='reference_with_documented_hota_changes'
            row['version_notes']=notes
            row['summary']+=' '+' '.join(notes)
        # Original ability tags must agree with the corrected effects.
        if i==130:
            row['tags']=[t for t in row['tags'] if t=='летающий' or t not in ('spell_school_immunity',)]
            row['tags'].append('spell_damage_reduction')
