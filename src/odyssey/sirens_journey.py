"""Revision 11: stronger sea ambushes and a real stop on the Sirens' island."""
from copy import deepcopy
from dataclasses import replace

from h3m import catalog
from h3m.adventure import Reward, read_monster, read_reward
from h3m.authored import monster
from h3m.build import sign_payload
from h3m.pacing import obstacle_cells, shortest_route, audit_landings
from odyssey.small_company import _reward
from odyssey.tempered_journey import generate as previous
from odyssey.playable import validate

SIRENS_COUNT = 200
AMBUSH_MULTIPLIER = 3
# Native creature 97 is Ancient Behemoth; Thunderbirds are 93.
ANCIENT_BEHEMOTH = 97
SIRENS_AMBUSH_COUNT = 5
LESSON_GUARDS = ((115,8),(153,40))
LESSON = 'Чаша тишины'
SIRENS_TEXT = ('Песня сирен заглушает команды. Прорвитесь через отряд в проливе, не теряя строй. '
               'В глубине острова стоит каменная чаша; вокруг неё не слышно ни одной песни.')


def _add_lesson(m,r,assets):
    key='sirens'
    land=set(map(tuple,next(i['protected_cells'] for i in r['layout'] if i['key']==key)))
    dock=next(tuple(h['beach']) for h in r['landings']['harbours'] if h['island']==key)
    t=assets.get(6);dx,dy=t.visitable_cells()[0]
    # IDs are integers in Reward's strict native layout: Wisdom=7, Expert=3.
    reward=Reward('Духи прибоя стерегут каменную чашу. За их спинами шум моря стихает. '
                  'Вы решаете пройти испытание тишины.',guards=LESSON_GUARDS,skills=((7,3),),mana=30)
    def footprint(o):
        template=m.object_templates[o.template_index]
        return {(o.x+x,o.y+y,o.z) for x,y in set(template.blocked_cells())|set(template.visitable_cells())}
    for visit in sorted(land,key=lambda c:(abs(c[0]-64)+abs(c[1]-26),c)):
        anchor=(visit[0]-dx,visit[1]-dy,visit[2])
        cells={(anchor[0]+x,anchor[1]+y,anchor[2]) for x,y in set(t.blocked_cells())|set(t.visitable_cells())}
        if not cells<=land or dock in cells:continue
        overlaps=[o for o in m.objects if footprint(o)&cells]
        if any(not 114<=o.object_id<=161 or not footprint(o)<=land for o in overlaps):continue
        original=list(m.objects)
        for o in overlaps:m.objects.remove(o)
        catalog.place(m,catalog.BorrowedObject(t,reward.pandora(),'sirens island lesson'),*anchor)
        obj=m.objects[-1]
        action=dict(island=key,label=LESSON,object_id=6,position=list(obj.position),visit=list(visit))
        try:
            blocked=obstacle_cells(m)
            for a in [*r['action_sites'],action]:
                if a['island']!=key:continue
                x,y,z=a['visit'];origin=tuple(a.get('origin',dock))
                route=shortest_route(m,origin,(x,y+1,z),blocked=blocked,land_only=True,diagonal=False)
                if len(route)-1>12:raise ValueError('Sirens lesson obstructs shore access')
        except ValueError:
            m.objects[:]=original
            continue
        r['action_sites'].append(action)
        r['choices'].append(dict(island=key,title=LESSON,position=list(obj.position),optional=True,
            guards=reward.guards,army=(),resources=(0,)*7,artifacts=(),spells=(),experience=0,
            mana=30,primary=(0,)*4,skills=reward.skills))
        return dict(position=list(obj.position),visit=list(visit),guards=LESSON_GUARDS,
            secondary_skill=dict(id=7,name='Мудрость',level=3,level_name='Экспертный'),
            mana=30,one_time=True,optional=True,
            note='Native guarded Pandora; consumed after taking its reward. Wisdom is raised to Expert, not above it.')
    raise ValueError('No accessible Sirens island lesson placement')


def generate(assets,seed=20260905):
    m,r=previous(assets,seed)
    r['gameplay_revision']=11
    changes=[]
    for a in r['ambushes']:
        o=next(o for o in m.objects if o.object_id==26 and list(o.position)==a['position'])
        old=_reward(read_reward(o.payload,event=True))
        guards=tuple((c,n*AMBUSH_MULTIPLIER) for c,n in old.guards)
        if a['island']=='sirens':
            guards=((ANCIENT_BEHEMOTH,SIRENS_AMBUSH_COUNT),)
        o.payload=replace(old,guards=guards).event()
        a['guards']=guards
        changes.append(dict(island=a['island'],position=a['position'],before=old.guards,after=guards))
    b=next(b for b in r['encounters'] if b['identifier']==40002)
    o=next(o for o in m.objects if o.object_id==54 and list(o.position)==b['position'])
    d=read_monster(o.payload)
    o.payload=monster(d['identifier'],SIRENS_COUNT,d['message'],d.get('artifact',65535),
        resources=d.get('resources',(0,)*7),upgraded_stack=0,stack_count=3)
    b['count']=SIRENS_COUNT
    for e in r['sea_encounters']:
        if e['identifier']==40002:e['count']=SIRENS_COUNT
    r['sirens_lesson']=_add_lesson(m,r,assets)
    r['objectives']['sirens']=SIRENS_TEXT
    for s in r['scenes']:
        if s['island']!='sirens':continue
        o=next(o for o in m.objects if o.object_id==26 and list(o.position)==s['position'])
        o.payload=replace(_reward(read_reward(o.payload,event=True)),message=SIRENS_TEXT).event()
        s['message']=SIRENS_TEXT
    for a in r['action_sites']:
        if a['island']=='sirens' and a['object_id']==91:
            o=next(o for o in m.objects if o.object_id==91 and list(o.position)==a['position'])
            o.payload=sign_payload('Среди скал стоит чаша тишины. Духи прибоя охраняют её от тех, кто поддался песне.'.encode('cp1251'))
    r['balance']['counts']['40002']=SIRENS_COUNT
    r['balance']['sea_revision']=dict(ambush_multiplier=AMBUSH_MULTIPLIER,ambushes=changes,
        ambush_overrides={'sirens':dict(creature_id=ANCIENT_BEHEMOTH,count=SIRENS_AMBUSH_COUNT)},
        sirens_count=SIRENS_COUNT,native_combat_verified=False)
    r['reward_policy']['total_cache_mana']=sum(read_reward(o.payload)['mana'] for o in m.objects if o.object_id==6)
    r['total_battles']+=1
    r['objects']=len(m.objects)
    m.header.description=('Одиссея, редакция 11. Усиленные морские засады и две сотни сирен; после сирен — 5 древних чудищ. '
        'На острове сирен — испытание мудрости и чаша тишины. Мастерская у Трои, меч Эола и возвращение к растущей армии Антиноя.').encode('cp1251')
    r.update(validate(m,r))
    optional={tuple(c['position']) for c in r['choices'] if c['optional']}
    mandatory=deepcopy(m)
    mandatory.objects=[o for o in mandatory.objects if o.object_id!=83 and not(o.object_id==6 and o.position in optional)]
    r['mandatory_without_optional']=validate(mandatory,r)['sequential_playthrough_model']
    r['fork']['verified_alternatives']={str(uid):validate(m,r,avoid_battles={uid})['sequential_playthrough_model'] for uid in r['optional_monster_ids']}
    docks={h['island']:tuple(h['beach']) for h in r['landings']['harbours']}
    r['landings']=audit_landings(m,docks)
    solid=obstacle_cells(m);routes=[]
    for a in r['action_sites']:
        x,y,z=a['visit'];origin=tuple(a.get('origin',docks.get(a['island'],(62,8,1))))
        route=shortest_route(m,origin,(x,y+1,z),blocked=solid,land_only=True,diagonal=False)
        if len(route)-1>12:raise ValueError('Sirens lesson exceeds shore travel budget')
        routes.append(dict(island=a['island'],label=a['label'],steps=len(route)-1))
    r['shore_access']=dict(routes=routes,max_steps=max(a['steps'] for a in routes))
    return m,r
