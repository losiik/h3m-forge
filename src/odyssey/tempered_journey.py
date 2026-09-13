"""Revision 10: early resistance, Aeolus' sword and an expedition workshop."""
from copy import deepcopy
from dataclasses import replace

from h3m import catalog
from h3m.adventure import read_monster, read_reward
from h3m.authored import monster, seer
from h3m.pacing import obstacle_cells, shortest_route, audit_landings
from odyssey.small_company import _reward
from odyssey.siege_journey import generate as previous
from odyssey.playable import validate

# Native IDs: VCMI config/artifacts.json, constants/EntityIdentifiers.h.
SWORD_OF_HELLFIRE = 11
WAR_MACHINE_FACTORY = 106
PURCHASE_FUND = 2250  # HotA: ballista 1500 + first aid tent 750.
EARLY_COUNTS = {50000:16, 30040:16, 50001:8, 40000:6}
BOX_GUARDS = {
    ('troy', 'optional'): ((0,8),(2,3)),
    ('lotus', 'main'): ((86,6),(84,8)),
    ('lotus', 'optional'): ((86,6),(87,3)),
    ('lotus', 'training'): ((86,6),(84,6)),
    ('cyclops', 'main'): ((0,10),(2,4)),
    ('lights', 'optional'): ((115,5),(153,8)),
    ('giants', 'optional'): ((87,7),(86,10)),
    ('giants', 'training'): ((87,8),(84,10)),
    ('circe', 'main'): ((86,9),(87,4)),
    ('circe', 'training'): ((115,8),(153,10)),
    ('sirens', 'optional'): ((115,8),(153,16)),
    ('calypso', 'main'): ((115,6),(153,12)),
    ('calypso', 'optional'): ((115,8),(153,12)),
}
AMBUSH_GUARDS = {
    'ismar': ((153,15),(115,3)),
    'lights': ((115,6),(153,10)),
    'sirens': ((97,6),),
}


def _place_workshop(m,r,assets):
    """Keep native footprint, every interaction and the beach accessible."""
    land=set(map(tuple,next(i['protected_cells'] for i in r['layout'] if i['key']=='troy')))
    beach=next(tuple(h['beach']) for h in r['landings']['harbours'] if h['island']=='troy')
    t=assets.get(WAR_MACHINE_FACTORY)
    dx,dy=t.visitable_cells()[0]
    def footprint(o):
        template=m.object_templates[o.template_index]
        return {(o.x+x,o.y+y,o.z) for x,y in set(template.blocked_cells())|set(template.visitable_cells())}
    for visit in sorted(land,key=lambda c:(abs(c[0]-10)+abs(c[1]-64),c)):
        anchor=(visit[0]-dx,visit[1]-dy,visit[2])
        cells={(anchor[0]+x,anchor[1]+y,anchor[2]) for x,y in set(t.blocked_cells())|set(t.visitable_cells())}
        if not cells<=land or beach in cells:continue
        overlaps=[o for o in m.objects if footprint(o)&cells]
        if any(not 114<=o.object_id<=161 or not footprint(o)<=land for o in overlaps):continue
        original=list(m.objects)
        for o in overlaps:m.objects.remove(o)
        catalog.place(m,catalog.BorrowedObject(t,b'','expedition workshop'),*anchor)
        obj=m.objects[-1]
        row=dict(island='troy',label='Мастерская боевых машин',object_id=WAR_MACHINE_FACTORY,
                 position=list(obj.position),visit=list(visit))
        try:
            solid=obstacle_cells(m)
            for a in [*r['action_sites'],row]:
                if a['island']!='troy':continue
                v=a['visit']
                route=shortest_route(m,beach,(v[0],v[1]+1,v[2]),blocked=solid,land_only=True,diagonal=False)
                if len(route)-1>12:raise ValueError('Workshop blocks an island interaction')
        except ValueError:
            m.objects[:]=original
            continue
        r['action_sites'].append(row)
        return dict(position=list(obj.position),visit=list(visit),island='troy',object_id=WAR_MACHINE_FACTORY,
            animation=t.animation_file.decode('ascii'),gold_fund=PURCHASE_FUND,
            prices=dict(ballista=1500,first_aid_tent=750),native_purchase_verified=False)
    raise ValueError('No accessible native war machine factory placement on Troy')


def generate(assets,seed=20260905):
    m,r=previous(assets,seed)
    r['gameplay_revision']=10
    for b in r['encounters']:
        if b['identifier'] not in EARLY_COUNTS:continue
        o=next(o for o in m.objects if o.object_id==54 and list(o.position)==b['position'])
        d=read_monster(o.payload);b['count']=EARLY_COUNTS[b['identifier']]
        o.payload=monster(d['identifier'],b['count'],d['message'],d.get('artifact',65535),
            resources=d.get('resources',(0,)*7),upgraded_stack=0,stack_count=d['stack_count'])
    for b in r['sea_encounters']:
        b['count']=next(e['count'] for e in r['encounters'] if e['identifier']==b['identifier'])

    changed=[]
    for c in r['choices']:
        key=(c['island'], 'training' if c['title']=='Испытание наставника' else 'optional' if c['optional'] else 'main')
        if key not in BOX_GUARDS:continue
        o=next(o for o in m.objects if o.object_id==6 and o.position==tuple(c['position']))
        old=_reward(read_reward(o.payload))
        reward=replace(old,guards=BOX_GUARDS[key])
        if c['island']=='troy':
            reward=replace(reward,resources=(0,0,0,0,0,0,PURCHASE_FUND),
                message='Вы отбили обоз мастеров. В сундуке лежит плата за походные машины. Мастерская стоит у дороги к пристани; баллиста и палатка пригодятся уже в следующем бою.')
        o.payload=reward.pandora()
        c.update(guards=reward.guards,resources=reward.resources)
        changed.append(dict(island=c['island'],position=c['position'],before=old.guards,after=reward.guards))
    for a in r['ambushes']:
        o=next(o for o in m.objects if o.object_id==26 and list(o.position)==a['position'])
        reward=replace(_reward(read_reward(o.payload,event=True)),guards=AMBUSH_GUARDS[a['island']])
        o.payload=reward.event();a['guards']=reward.guards

    for q in r['quests']:
        if q['island']=='aeolus':
            q.update(reward=SWORD_OF_HELLFIRE,
                first='Усмирите бурю у берега. Тогда Эол откроет свой походный арсенал.',
                done='Эол вручает Меч адского пламени. Его лезвие прибавляет шесть к нападению. Зелёные драконы стерегут сад: этот бой станет испытанием нового оружия.')
        elif q['island']=='calypso':
            # Removing the orb reward must not leave an unsatisfiable exchange.
            # The sword is retained; the cloak is earned by the existing local battle.
            q.update(mission=4,required=(70019,),
                first='Победите стража Калипсо на берегу. Она признает тех, кто сумеет уйти.',
                done='Страж повержен. Калипсо отдаёт Плащ скорости ветра; меч остаётся у вас.')
        else:continue
        o=next(o for o in m.objects if o.object_id==83 and list(o.position)==q['position'])
        o.payload=seer(q['required'],q['reward'],q['first'],q['done'],mission=q['mission'],reward_kind=q['reward_kind'])
    r['chapters']=list(r['quests'])
    r['workshop']=_place_workshop(m,r,assets)
    r['balance']['counts']={str(b['identifier']):b['count'] for b in r['encounters']}
    r['balance']['early_revision']=dict(boxes=changed,ambushes=AMBUSH_GUARDS,green_dragons=2,
        sword_id=SWORD_OF_HELLFIRE,sword_attack_bonus=6,native_combat_verified=False)
    r['reward_policy']['purchase_fund']=PURCHASE_FUND
    r['objects']=len(m.objects)
    m.header.description=('Одиссея, редакция 10. Усиленные ранние бои и засады, малый отряд, ограниченная мана. '
        'Мастерская у Трои; меч Эола перед зелёными драконами. Антиной нанимает стрелков, пока вы возвращаетесь на Итаку.').encode('cp1251')
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
        path=shortest_route(m,origin,(x,y+1,z),blocked=solid,land_only=True,diagonal=False)
        if len(path)-1>12:raise ValueError('Workshop exceeds shore travel budget')
        routes.append(dict(island=a['island'],label=a['label'],steps=len(path)-1))
    r['shore_access']=dict(routes=routes,max_steps=max(a['steps'] for a in routes))
    return m,r
