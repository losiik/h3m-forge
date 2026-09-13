"""Revision 6: a gated sea maze with optional coves and gradual exploration."""
from copy import deepcopy
from dataclasses import replace

from h3m import catalog
from h3m.adventure import Reward, read_reward, edit_monster, timed_message
from h3m.pacing import obstacle_cells, audit_landings, audit_sea_legs, shortest_route
from odyssey import payloads as p
from odyssey.compact import generate as compact, ISLANDS, SEA_ORDER
from odyssey.navigation import harbours
from odyssey.playable import validate
from odyssey.maze_coast import carve
from odyssey.labyrinth_text import TASKS, DONE


CHECKPOINTS = dict(ismar=(16,62),lotus=(16,44),cyclops=(16,26),aeolus=(22,17),
    lights=(34,26),giants=(40,20),circe=(53,18),sirens=(70,26),scylla=(70,44),
    helios=(70,62),calypso=(53,71),phaeacia=(26,70),ithaca=(34,62))
SEGMENTS = (
    ((8,71),(18,71)),((18,71),(18,68)),((18,68),(16,68)),((16,68),(16,58)),
    ((16,58),(18,58)),((18,58),(18,50)),((18,50),(16,50)),((16,50),(16,40)),
    ((16,40),(18,40)),((18,40),(18,32)),((18,32),(16,32)),((16,32),(16,22)),
    ((16,22),(18,22)),((18,22),(18,17)),((8,17),(30,17)),
    ((30,17),(30,18)),((30,18),(38,18)),((38,18),(38,20)),((38,20),(48,20)),
    ((48,20),(48,18)),((48,18),(56,18)),((56,18),(56,16)),((56,16),(64,16)),
    ((64,16),(64,18)),((64,18),(70,18)),((44,20),(44,17)),((62,16),(62,17)),
    ((70,18),(70,22)),((70,22),(68,22)),((68,22),(68,24)),((68,24),(70,24)),((70,24),(70,32)),((70,32),(68,32)),((68,32),(68,40)),((68,40),(70,40)),((70,40),(70,50)),((70,50),(68,50)),((68,50),(68,58)),((68,58),(70,58)),((70,58),(70,68)),((70,68),(68,68)),((68,68),(68,71)),((68,71),(70,71)),((70,71),(26,71)),((34,71),(34,53)),((34,53),(26,53)),
    ((18,53),(8,53)),((18,35),(8,35)),
    ((70,35),(62,35)),((70,53),(62,53)),
    ((34,18),(34,35)),((34,35),(26,35)),
    # Two genuine optional detours return to the same main-route junction.
    ((46,20),(46,30)),((46,30),(42,30)),((42,30),(42,28)),
    ((62,35),(52,35)),((52,35),(52,48)),((52,48),(48,48)),((48,48),(48,46)),
)
START_ARMY=((1,20),(3,12),(6,8),(0,6))
# Deliberate escalation; player reinforcements are paced by chapter below.
COUNTS={50000:32,30040:58,50001:30,30042:16,30044:34,30045:100,
        40000:28,40001:42,40002:68,40003:45,40004:44,40005:85,40006:44,50002:56}


def generate(assets,seed=20260905,*,extra_segments=()):
    m,r=compact(assets,seed)
    docks=harbours(m,ISLANDS)
    m.header.name='Одиссея: лабиринт Посейдона'.encode('cp1251')
    m.header.description=('От Трои к Итаке через извилистые проливы, закрытые бухты и боковые гроты. '
        'Разведывайте путь сами: следующий участок открывается после испытания. '
        'Раскрытие меха — бой с ветрами; искать корону не нужно. '
        'Один герой, сложность 100%. Новая игра; баланс требует игрового прогона.').encode('cp1251')
    m.objects=[o for o in m.objects if o.object_id not in (27,37,59)]
    r['action_sites']=[a for a in r['action_sites'] if a['object_id']!=37]
    hero=next(o for o in m.objects if o.object_id==34)
    hero.payload=p.hero(army=START_ARMY,artifacts=(),spells=(27,41),equipped={0:136})

    def move(o,visit):
        t=m.object_templates[o.template_index]
        dx,dy=t.visitable_cells()[0]
        o.x,o.y,o.z=visit[0]-dx,visit[1]-dy,visit[2]

    # Replace the invisible crown handoff with a native remembered victory.
    wind_id=60000
    q=next(q for q in r['quests'] if q['reward']==21)
    hut=next(o for o in m.objects if o.object_id==83 and list(o.position)==q['position'])
    q.update(mission=4,required=(wind_id,),first='Вырвавшиеся ветры бушуют в боковом проливе. Укротите их и вернитесь к Эолу.',
             done='Эол отказывает в новом мехе. За восточной расселиной лежит гавань лестригонов.')
    hut.payload=p.seer(q['required'],21,q['first'],q['done'],mission=4)
    event=next(o for o in m.objects if o.object_id==26 and any(a==22 for a,s in read_reward(o.payload,event=True)['artifacts']))
    m.objects.remove(event)
    t=replace(assets.get(54,115),terrain_mask=assets.get(54,115).terrain_mask|256)
    dx,dy=t.visitable_cells()[0]
    catalog.place(m,catalog.BorrowedObject(t,p.monster(wind_id,30,'Мех раскрыт! Вырвавшиеся ветры бросают корабль на скалы.',65535),'escaped winds'),26-dx,33-dy,0)
    wind=m.objects[-1]
    battle=dict(island='lights',identifier=wind_id,position=list(wind.position),creature=115,count=30)
    r['encounters'].append(battle);r['sea_encounters'].append(battle)
    r['scenes']=[s for s in r['scenes'] if s['island']!='lights']

    # Gates now close the route itself, not a bay that the player can sail past.
    for g in r['harbour_guards']:
        if g['island']=='hades':continue
        o=next(o for o in m.objects if o.object_id==215 and list(o.position)==g['position'])
        target=(*CHECKPOINTS[g['island']],0);move(o,target)
        g['position']=list(o.position)
        o.payload=p.quest(g['required'],'Проход закрыт: завершите испытание в предыдущей бухте.',
                          'Путь свободен. Следуйте по открывшемуся проливу.',mission=g['mission'])

    # New optional coves have visible guarded rewards and a single return path.
    bays=[('grove','giants',42,27,'Грот уцелевших',((87,28),(86,45)),((3,12),(6,6))),
          ('wreck','sirens',48,45,'Затонувшая ахейская казна',((115,36),(153,70)),((3,14),(6,10)))]
    bay_land=set()
    for key,parent,x,y,title,guards,army in bays:
        for yy in range(y-3,y+1):
            for xx in range(x-2,x+2):
                bay_land.add((xx,yy,0))
        choice=next(c for c in r['choices'] if c['optional'] and c['island']==('ismar' if key=='grove' else 'sirens'))
        obj=next(o for o in m.objects if o.object_id==6 and list(o.position)==choice['position'])
        oldpos=choice['position'];move(obj,(x,y-1,0))
        obj.payload=Reward(title+'. Бухта в стороне от пути. Сразиться за спасённых моряков или вернуться в пролив?',
            guards=guards,army=army,experience=1400 if key=='grove' else 2200).pandora()
        choice.update(position=list(obj.position),island=parent,title=title,guards=guards,army=army,spells=(),mana=0)
        for a in r['action_sites']:
            if a['object_id']==6 and a['position']==oldpos:
                a.update(position=list(obj.position),visit=[x,y-1,0],origin=[x,y,0],label=title)
        docks[key]=(x,y,0)

    protected={tuple(c) for room in r['layout'] if room['center'][2]==0 for c in room['protected_cells']}
    converted,counts,shore_walls=carve(m,assets,SEGMENTS+tuple(extra_segments),docks,protected,bay_land,seed)

    # Close full corridor cross-sections, leaving exactly one gate tile. The
    # long sections prevent diagonal cuts around the edge of a one-tile lock.
    reef=next(t for ts in assets.templates.values() for t in ts if t.object_id in (147,161)
              and t.blocked_cells()==[(0,0)] and not t.visitable_cells() and t.allows_terrain(8))
    solid=obstacle_cells(m);walls=[]
    for key,(x,y) in CHECKPOINTS.items():
        horizontal=key in ('aeolus','giants','circe','calypso')
        for c in ((x,yy,0) for yy in range(max(0,y-2),min(72,y+3))) if horizontal else ((xx,y,0) for xx in range(max(0,x-2),min(72,x+3))):
            if c==(x,y,0) or c in solid:continue
            if not m.terrain.tile(*c).is_water:raise ValueError(f'Unblocked land at lock {key}: {c}')
            catalog.place(m,catalog.BorrowedObject(reef,b'','maze choke'),*c);solid.add(c);walls.append(c)

    # Fixed monsters do not grow with calendar days. More opposition early,
    # smaller and later reinforcements; mass Slow/Haste is earned, not initial.
    for b in r['encounters']:
        if b['identifier'] not in COUNTS:continue
        obj=next(o for o in m.objects if o.object_id==54 and list(o.position)==b['position'])
        b['count']=COUNTS[b['identifier']];obj.payload=edit_monster(obj.payload,count=b['count'])
    for c in r['choices']:
        if c['title']!='Союзники пополняют отряд':continue
        obj=next(o for o in m.objects if o.object_id==6 and list(o.position)==c['position'])
        army=((3,8),(6,6)) if c['island'] in ('aeolus','circe') else ((3,12),(6,10))
        spells=(54,) if c['island']=='circe' else (53,) if c['island']=='calypso' else ()
        obj.payload=Reward('Уцелевшие моряки присоединяются к кораблю.',army=army,spells=spells,experience=500).pandora()
        c.update(army=army,spells=spells)

    # Short local fiction replaces coordinate instructions. Physical passages
    # carry navigation; signs remain an optional reminder of the local task.
    objectives=dict(TASKS)
    for q in r['quests']:
        obj=next(o for o in m.objects if o.object_id==83 and list(o.position)==q['position'])
        first=TASKS[q['island']]
        if q['reward']==21:first='Вторая встреча с Эолом. Сначала усмирите ветры в рукаве у огней родины.'
        if q['reward']==15:first='Последний совет Кирки. Сначала выслушайте Тиресия за подземными вратами.'
        q.update(first=first,done=DONE[q['reward']])
        obj.payload=p.seer(q['required'],q['reward'],first,q['done'],mission=q['mission'])
    for q in r['bargains']:
        obj=next(o for o in m.objects if o.object_id==83 and list(o.position)==q['position'])
        obj.payload=p.seer((0,0,0,0,0,0,q['price']),q['reward'],TASKS[q['island']],DONE[q['reward']],mission=7)
    for b in r['encounters']:
        obj=next(o for o in m.objects if o.object_id==54 and list(o.position)==b['position'])
        obj.payload=edit_monster(obj.payload,message=TASKS[b['island']])
    for o in m.objects:
        if o.object_id==26:
            # Arrival rewards are small recovery stops; no global scouting.
            scene=next(s for s in r['scenes'] if s['position']==list(o.position))
            scene['message']=TASKS[scene['island']]
            o.payload=Reward(scene['message'],mana=5,movement=250).event()
        elif o.object_id==91:
            from h3m.build import sign_payload
            key=min((i for i in ISLANDS if i.z==o.z),key=lambda i:abs(o.x-i.x)+abs(o.y-i.y)).key
            o.payload=sign_payload(objectives[key].encode('cp1251'))
    m.events.events=[timed_message('Из пепла Трои','Троянский дозор отрезал путь к кораблю. Отбейте его и выходите из бухты. '
        'Дальше вас поведут проливы. В боковых гротах можно искать союзников, затем возвращаться тем же путём. '
        'Шляпа адмирала сохраняет движение при высадке. Потеря Одиссея означает поражение.')]
    r.update(gameplay_revision=6,landscape_revision=2,name=m.header.name_text,objects=len(m.objects),objectives=objectives,
        guidance=dict(revision=2,scouting_hut=None,eyes=[],bottles=[],progressive_exploration=True),
        labyrinth=dict(revision=2,shore_walls=shore_walls,main_segments=SEGMENTS,checkpoints=CHECKPOINTS,blocked_mainland=sorted(converted),
                       wall_cells=walls,land_objects=dict(counts),optional_coves=[dict(key=b[0],dock=docks[b[0]],parent=b[1]) for b in bays]),
        balance=dict(starting_army=START_ARMY,starting_spells=(27,41),counts=COUNTS,
                     assumptions='Authored escalation; no tactical battle simulator or full playtest.'),
        crown_dependency_removed=True,native_editor_checked=False,full_playtest=False)
    r['barriers']=dict(revision=2,blocked_land_cells=sorted(converted),land_objects=dict(counts),
        shoreline_cells=shore_walls,gate_wall_cells=walls,
        model='Continuous blocked mainland with native scenery masks and localized shore barriers.')
    r['reefs']=sum(o.object_id in (147,161) for o in m.objects)
    r['decorations']=sum(114<=o.object_id<=140 for o in m.objects)
    r.pop('reef_wall_cells_before',None)
    r['total_battles']=len(r['encounters'])+sum(bool(c['guards']) for c in r['choices'])
    r['sea_battles']=len(r['sea_encounters'])
    r.update(validate(m,r))
    mandatory=deepcopy(m)
    optional={tuple(c['position']) for c in r['choices'] if c['optional']}
    optional_huts={tuple(c['position']) for c in r['bargains']}
    mandatory.objects=[o for o in mandatory.objects if not(o.object_id==6 and o.position in optional)
                       and not(o.object_id==83 and o.position in optional_huts)]
    r['mandatory_without_optional']=validate(mandatory,r)['sequential_playthrough_model']
    r['landings']=audit_landings(m,docks)
    solid=obstacle_cells(m);routes=[]
    for a in r['action_sites']:
        origin=tuple(a.get('origin',docks.get(a['island'],(62,8,1))))
        x,y,z=a['visit']
        path=shortest_route(m,origin,(x,y+1,z),blocked=solid,land_only=True,diagonal=False)
        routes.append(dict(island=a['island'],label=a['label'],steps=len(path)-1))
    r['shore_access']=dict(routes=routes,max_steps=max(a['steps'] for a in routes),model='Cardinal approaches after final mainland and decoration placement.')
    r['pacing']=audit_sea_legs(m,[(a+' → '+b,(docks[a][0],docks[a][1]+4,0),
        (docks[b][0],docks[b][1]+4,0)) for a,b in zip(SEA_ORDER,SEA_ORDER[1:])],max_steps=30)
    return m,r
