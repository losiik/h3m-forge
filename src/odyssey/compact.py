"""Revision 4: a compact sea adventure; travel has an explicit distance budget."""
from copy import deepcopy
from dataclasses import replace
from math import hypot
from random import Random

from h3m import catalog, conditions
from h3m.adventure import Reward, timed_message
from h3m.build import sign_payload
from h3m.pacing import audit_landings, audit_sea_legs, obstacle_cells, shortest_route
from h3m.terrain import Terrain, TerrainMap
from h3m.world import scenery_for
from odyssey import payloads as p
from odyssey.navigation import harbours, land_of
from odyssey.playable import generate as previous, validate, START_ARMY, TACTICAL_SPELLS
from odyssey.story import ISLANDS as OLD_ISLANDS, Island


CENTERS=dict(troy=(8,62),ismar=(8,44),lotus=(8,26),cyclops=(8,8),aeolus=(26,8),
    lights=(26,26),giants=(44,8),circe=(62,8),sirens=(62,26),scylla=(62,44),
    helios=(62,62),calypso=(44,62),phaeacia=(26,62),ithaca=(26,44),hades=(62,8))
ISLANDS=tuple(Island(i.key,i.name,*CENTERS[i.key],i.terrain,6,i.z) for i in OLD_ISLANDS)
SEA_ORDER=('troy','ismar','lotus','cyclops','aeolus','lights','aeolus','giants','circe',
           'sirens','scylla','helios','calypso','phaeacia','ithaca')


def landscape():
    n=72
    data=bytearray(bytes([8,0,0,0,0,0,0])*n*n+bytes([9,0,0,0,0,0,0])*n*n)
    for i in ISLANDS:
        for y in range(i.y-6,i.y+6,2):
            for x in range(i.x-6,i.x+6,2):
                if hypot(x+1-i.x,y+1-i.y)>6:
                    continue
                for dy in (0,1):
                    for dx in (0,1):
                        data[((i.z*n+y+dy)*n+x+dx)*7]=i.terrain
    return TerrainMap(bytes(data),n,2)


def generate(assets,seed=20262905):
    m,old=previous(assets,seed)
    previous_map=deepcopy(m)
    originals={(o.object_id,o.position):o for o in m.objects}
    islands={i.key:i for i in ISLANDS}
    m.header.size=72
    m.header.name='Одиссея: тесные проливы'.encode('cp1251')
    m.header.description=('Переработка 4. Компактный архипелаг 72x72: короткие переходы, '
        'шляпа адмирала со старта, бои и решения рядом с пристанями. '
        'От Трои до Пенелопы. Сложность 100%. Баланс требует игрового прогона.').encode('cp1251')
    m.terrain=landscape(); assets.terrain.apply(m.terrain,seed=seed)
    m.objects=[]
    docks=harbours(m,ISLANDS)
    lands={i.key:land_of(m,i) for i in ISLANDS}
    occupied=set(); approaches=set(); records=[]
    reserved={(x,yy,z) for key,(x,y,z) in docks.items() for yy in range(islands[key].y-3,y+1)}

    def put(kind,visit,payload=b'',sub=0,*,near=False,water=False):
        t=assets.get(kind,sub)
        if water: t=replace(t,terrain_mask=t.terrain_mask | (1<<8))
        dx,dy=t.visitable_cells()[0] if t.visitable_cells() else (0,0)
        candidates=[visit]
        if near:
            x,y,z=visit
            candidates=[(x+xx,y+yy,z) for yy in range(-5,6) for xx in range(-5,6)]
            candidates.sort(key=lambda c:(abs(c[0]-x)+abs(c[1]-y),c[1],c[0]))
        for cell in candidates:
            anchor=(cell[0]-dx,cell[1]-dy,cell[2])
            footprint={(anchor[0]+a,anchor[1]+b,anchor[2]) for a,b in set(t.blocked_cells())|set(t.visitable_cells())}
            solid={(anchor[0]+a,anchor[1]+b,anchor[2]) for a,b in t.blocked_cells() if (a,b) not in t.visitable_cells()}
            approach=(cell[0],cell[1]+1,cell[2])
            if footprint & occupied or solid & (reserved|approaches): continue
            if any(not (0<=a<72 and 0<=b<72) or m.terrain.tile(a,b,c).terrain==9
                   or (not water and m.terrain.tile(a,b,c).is_water) for a,b,c in footprint): continue
            if near and (approach in occupied or m.terrain.tile(*approach).terrain in (8,9)): continue
            catalog.place(m,catalog.BorrowedObject(t,payload,'compact adventure'),*anchor)
            occupied.update(footprint)
            if near: approaches.add(approach)
            return m.objects[-1]
        raise ValueError(f'No compact placement for {kind}/{sub} at {visit}')

    def local(key,offset):
        i=islands[key]; return i.x+offset[0],i.y+offset[1],i.z
    def record(o,key,label):
        t=m.object_templates[o.template_index]; dx,dy=t.visitable_cells()[0]
        records.append(dict(island=key,label=label,object_id=o.object_id,position=list(o.position),
                            visit=[o.x+dx,o.y+dy,o.z]))

    # Keep a town to avoid the seven-day townless loss. Its footprint fits a bay.
    for key in ('troy','ithaca'):
        o=put(98,local(key,(-1,-2)),p.town('Ахейская стоянка' if key=='troy' else 'Дворец Одиссея',0 if key=='troy' else 255),near=True)
        if key=='troy': m.players[0].main_town_pos=(o.x-2,o.y,o.z)
    hero=put(34,local('troy',(0,2)),p.hero(army=START_ARMY,artifacts=(),spells=TACTICAL_SPELLS,equipped={0:136}),near=True)
    hero_t=m.object_templates[hero.template_index]; dx,dy=hero_t.visitable_cells()[0]
    start=(hero.x+dx,hero.y+dy,hero.z)
    # Native conditions refer to the hero's visit cell, not its sprite anchor.
    m.loss=conditions.LossCondition(conditions.LossType.LOSE_HERO,bytes(start))
    x,y,z=docks['troy']; put(8,(x,y+1,z),water=True)

    # Underworld is a short room. Both gates have matching native coordinates.
    portals=[]
    for z in (0,1):
        o=put(103,(62,4,z),near=False)
        t=m.object_templates[o.template_index]; dx,dy=t.visitable_cells()[0]
        portals.append((o.x+dx,o.y+dy,o.z))
    wall_y=7
    rock=next(t for ts in assets.templates.values() for t in ts if t.object_id==140
        and t.allows_terrain(Terrain.SUBTERRANEAN) and t.blocked_cells()==[(0,0)] and not t.visitable_cells())
    for c in sorted(lands['hades']):
        if c[1]==wall_y and c[0]!=62:
            catalog.place(m,catalog.BorrowedObject(rock,b'','underworld wall'),*c); occupied.add(c)

    # Every hint names actual coordinates, making direction changes unambiguous.
    objectives={}
    from odyssey.playable import OBJECTIVES
    for key,text in OBJECTIVES.items():
        objectives[key]=text
    objectives.update(
        troy='Разбейте дозор рядом со стоянкой. Корабль у южного пляжа. Затем Исмар (8,44). Шляпа адмирала уже надета: не снимайте её, чтобы посадка и высадка не съедали весь ход.',
        ismar='Отбейте киконов рядом с причалом. Можно рискнуть ради отставших лучников. Следом лотофаги (8,26).',
        lotus='Спасите разведчиков: победите разбойников и заберите пополнение рядом. В боковой роще можно добыть заклинание Точность. Далее Полифем (8,8).',
        cyclops='Побег, а не убийство: нужны 30 дерева и 1000 золота. Вино и кол охраняются рядом с пещерой. Подготовьте план в хижине, затем Эол (26,8).',
        aeolus='Западная хижина даёт мех ветров. Огни родины совсем рядом: (26,26). После раскрытия меха вернитесь в восточную хижину. Дальше лестригоны (44,8).',
        lights='Мех раскрыт, ветры уносят корабль от родины. Возвращайтесь к Эолу (26,8), в восточную хижину. Здесь больше заданий нет.',
        giants='Разбейте лестригонов у пристани. Потом к Кирке (62,8). Дальний обход океана больше не нужен.',
        circe='Отбейте 7 самоцветов в роще и поговорите с западной хижиной Кирки. Врата Тиресия на севере (62,4); выслушайте его и вернитесь в восточную хижину. Далее сирены (62,26).',
        hades='Поговорите с Тиресием сразу за стражем. Возвращайтесь через те же северные врата к Кирке. Подземное царство здесь — одна сцена.',
        sirens='Пройдите морской бой. Необязательный груз на рифах даёт заклинание Лечение и ману. Следом Сцилла (62,44).',
        scylla='Шесть копейщиков — цена спасения корабля. Запасные шестеро рядом. Завершите разговор со Сциллой; затем Гелиос (62,62).',
        helios='Спутники нарушили запрет Тиресия. Бой со стадом изображает это решение. Затем Калипсо (44,62).',
        calypso='Для плота нужны 20 дерева и 10 руды: сохраните свои или отбейте склад. Боковой грот даёт войска ценой боя. Затем феаки (26,62).',
        phaeacia='Победите бойцов Алкиноя. Большие состязания можно пропустить: они дают опыт и крестоносцев ценой потерь. Итака рядом, на севере (26,44).',
        ithaca='Победите женихов у дворца и поговорите с Пенелопой. Ничего собирать и относить по другим островам больше не нужно.')

    objectives['cyclops']='Подготовьте побег: западная хижина требует 30 дерева и 1000 золота; склад охраняется рядом. Альтернатива: мастер продаст готовый план за 7000 золота. Выбирайте трату денег или бой за припасы. Далее Эол (26,8).'
    objectives['circe']='Помощь Гермеса: отбейте 7 самоцветов и придите в западную хижину Кирки, либо заплатите мастеру 7000 золота за молю. Затем северные врата (62,4), Тиресий и восточная хижина Кирки. Далее сирены (62,26).'
    objectives['calypso']='Плот: отдайте 20 дерева и 10 руды в хижину Калипсо или купите готовый у мастера за 9000 золота. Материалы охраняются рядом. Сбережённые деньги или сбережённые люди? Далее феаки (26,62).'
    after={
        10:'Полифем пьян и ослеплён; вы спаслись под баранами. Не нужно никого убивать в пещере. Следующая цель: мех Эола, остров (26,8), западная хижина.',
        11:'Мех ветров у вас. Следующая цель: огни Итаки (26,26). После раскрытия меха вернитесь в восточную хижину Эола.',
        21:'Эол отказал в новой помощи. Следующая цель: гавань лестригонов (44,8), победить великанов.',
        13:'Молю разрушает чары, спутники снова люди. Следующая цель: Тиресий за северными вратами (62,4). Затем вернитесь в восточную хижину Кирки.',
        14:'Тиресий предостерегает от стад Гелиоса. Вы встретили тень матери. Следующая цель: восточная хижина Кирки через те же северные врата.',
        15:'Кирка дала воск и путы. Следующая цель: сирены (62,26). Сохраните шесть копейщиков для Сциллы.',
        17:'Шесть спутников погибли, корабль прошёл пролив. Следующая цель: стада Гелиоса (62,62).',
        19:'Плот готов. Одиссей отвергает бессмертие и отправляется домой. Следующая цель: феаки (26,62), состязания Алкиноя.',
        36:'Пенелопа узнаёт вас по тайне ложа, выросшего из живой оливы. После двадцати лет Одиссей дома.'}
    quests=[]; optional_quests=[]
    for q in old['quests']:
        key=q['island']; offset=(2,0) if q['reward'] in (21,15) else (-2,0)
        if key=='hades': offset=(-2,2)
        first=objectives[key]
        if q['reward']==21: first='Вторая встреча: сначала раскройте мех у огней родины (26,26). Затем вернитесь сюда.'
        if q['reward']==15: first='Второй разговор: выслушайте Тиресия за северными вратами и вернитесь сюда.'
        done=after[q['reward']]
        o=put(83,local(key,offset),p.seer(q['required'],q['reward'],first,done,mission=q['mission']),near=True)
        quests.append(dict(q,position=list(o.position),first=first,done=done)); record(o,key,q['title'])
        if q['reward'] in (10,13,19): optional_quests.append(list(o.position))
    bargains=[]
    for key,price,reward,title in (('cyclops',7000,10,'Мастер побега'),('circe',7000,13,'Молю у Гермеса'),('calypso',9000,19,'Готовый плот')):
        first=f'{title}. За {price} золота вы сразу завершите подготовку без боя за склад. Это альтернатива соседней хижине: оплачивать оба варианта не нужно.'
        req=(0,0,0,0,0,0,price)
        o=put(83,local(key,(3,-3)),p.seer(req,reward,first,after[reward],mission=7),near=True)
        optional_quests.append(list(o.position)); record(o,key,title)
        bargains.append(dict(island=key,title=title,price=price,reward=reward,position=list(o.position)))

    choices=[]
    for c in old['choices']:
        key=c['island']; reward=Reward('',guards=tuple(c['guards']),army=tuple(c['army']),
            resources=tuple(c['resources']),experience=c['experience'])
        title=c['title']; detail=''
        if c['optional'] and key=='lotus':
            reward=replace(reward,army=(),spells=(44,),mana=10); detail='Точность и 10 маны'
        elif c['optional'] and key=='sirens':
            reward=replace(reward,army=(),spells=(37,),mana=20); detail='Лечение и 20 маны'
        if detail:
            msg=f'{title}\nНЕОБЯЗАТЕЛЬНО. Можно отказаться. Награда: {detail}; {c["experience"]} опыта. Охрана: '
            from odyssey.playable import CREATURE_NAMES
            msg+='; '.join(f'{CREATURE_NAMES[a]} — {b}' for a,b in c['guards'])+'.'
        else:
            from h3m.adventure import read_reward
            msg=read_reward(originals[6,tuple(c['position'])].payload)['message']
        reward=replace(reward,message=msg)
        offset=(3,-2) if c['optional'] else (2,2)
        if c['title']=='Союзники пополняют отряд': offset=(3,1)
        if key=='scylla': offset=(2,1)
        o=put(6,local(key,offset),reward.pandora(),near=True)
        choices.append(dict(c,position=list(o.position),army=reward.army,spells=reward.spells,mana=reward.mana))
        record(o,key,title)

    battles=[]
    for b in old['encounters']:
        if b['identifier']>=40000 and b['identifier']<50000: continue
        key=b['island']; raw=originals[54,tuple(b['position'])].payload
        o=put(54,local(key,(2,0)),raw,b['creature'],near=True)
        battles.append(dict(b,position=list(o.position))); record(o,key,'Бой')

    # Same native quest conditions, rebuilt around the smaller coasts.
    reefs=set(); lanes=set(); gates=[]; scenes=[]
    sea_by_key={b['island']:b for b in old['sea_encounters']}
    for i in ISLANDS:
        key=i.key
        if i.z: continue
        land=lands[key]
        expanded=[]
        for d in (1,2):
            expanded.append({(x+xx,y+yy,z) for x,y,z in land for yy in range(-d,d+1) for xx in range(-d,d+1)
                             if 0<=x+xx<72 and 0<=y+yy<72})
        reefs.update(c for c in expanded[1]-expanded[0] if m.terrain.tile(*c).is_water)
        x,y,z=docks[key]
        lanes.update((x,yy,z) for yy in range(y+1,y+5))
        reefs.update((xx,yy,z) for xx in (x-1,x+1) for yy in range(y+1,y+4))
        if key=='troy': continue
        g=next(g for g in old['harbour_guards'] if g['island']==key)
        o=put(215,(x,y+3,z),p.quest(g['required'],i.name+'\n'+objectives[key],
            'Пролив открыт.\n'+objectives[key],mission=g['mission']),water=True)
        gates.append(dict(g,position=list(o.position)))
        if key in sea_by_key:
            b=sea_by_key[key]
            o=put(54,(x,y+1,z),originals[54,tuple(b['position'])].payload,b['creature'],water=True)
            battles.append(dict(b,position=list(o.position)))
        # Arrival message before fight; the winds token remains beyond the fight.
        cell=(x,y if key=='lights' else y+2,z)
        msg=i.name+'\n\n'+objectives[key]
        o=put(26,cell,Reward(msg,artifacts=(22,) if key=='lights' else (),movement=500,mana=10).event(),water=True)
        scenes.append(dict(island=key,position=list(o.position),message=msg))
    g=next(g for g in old['harbour_guards'] if g['island']=='hades')
    o=put(215,(62,wall_y,1),p.quest((13,),'Принесите знак Кирки.','Тиресий ждёт рядом.'))
    gates.append(dict(g,position=list(o.position)))
    reef_templates=sorted({t.animation_file:t for ts in assets.templates.values() for t in ts
        if t.object_id in (147,161) and t.allows_terrain(Terrain.WATER)
        and t.blocked_cells()==[(0,0)] and not t.visitable_cells()}.values(),key=lambda t:t.animation_file)
    reefs.difference_update(lanes)
    for n,c in enumerate(sorted(reefs)):
        if c in occupied: raise ValueError(f'Reef overlaps object {c}')
        catalog.place(m,catalog.BorrowedObject(reef_templates[n%len(reef_templates)],b'','reef'),*c)
        occupied.add(c)

    # Visible signs sit beside the actions, not at far corners of empty islands.
    for i in ISLANDS:
        o=put(91,local(i.key,(-1,3)),sign_payload((i.name+'\n'+objectives[i.key]).encode('cp1251')),near=True)
        record(o,i.key,'Указатель')
    # Reserve real routes to each southern interaction before adding scenery.
    blocked=obstacle_cells(m)
    for r in records:
        key=r['island']; v=tuple(r['visit']); approach=(v[0],v[1]+1,v[2])
        origin=docks[key] if key!='hades' else (62,8,1)
        reserved.update(shortest_route(m,origin,approach,blocked=blocked,land_only=True,diagonal=False))
    rng=Random(seed)
    all_land=set.union(*lands.values())
    points=sorted(all_land); rng.shuffle(points)
    for c in points:
        if c in occupied|reserved|approaches or rng.random()>.6: continue
        palette=scenery_for(assets,m.terrain.tile(*c).terrain)
        rng.shuffle(palette)
        for t in palette:
            footprint={(c[0]+a,c[1]+b,c[2]) for a,b in set(t.blocked_cells())|{(0,0)}}
            if footprint & (occupied|reserved|approaches): continue
            if not footprint<=all_land: continue
            catalog.place(m,catalog.BorrowedObject(t,b'','compact scenery'),*c); occupied.update(footprint); break

    m.events.events=[timed_message('Первый шаг', 'ОДИССЕЯ: ТЕСНЫЕ ПРОЛИВЫ\n\n'+objectives['troy']+
        '\n\nНа островах задача, припасы и выход находятся рядом. Дополнительные бои можно пропустить. '
        'Заклинания помогают сберечь войско. Победа — освободить Итаку и встретиться с Пенелопой.')]
    report=dict(old,gameplay_revision=4,name=m.header.name_text,size=72,objects=len(m.objects),
        quests=quests,chapters=quests,choices=choices,encounters=battles,scenes=scenes,harbour_guards=gates,
        sea_encounters=[b for b in battles if 40000<=b['identifier']<50000],objectives=objectives,
        reefs=len(reefs),start=start,teleport_pairs=[(portals[0],portals[1]),(portals[1],portals[0])],
        islands=[dict(key=i.key,name=i.name,center=[i.x,i.y,i.z]) for i in ISLANDS],
        layout=[dict(key=i.key,center=[i.x,i.y,i.z],radius=6,
            protected_cells=sorted(c for c in lands[i.key] if i.key!='hades' or c[1]>wall_y)) for i in ISLANDS],
        action_sites=records,admirals_hat_equipped=True,bargains=bargains,
        optional_quest_positions=optional_quests,decorations=sum(114<=o.object_id<=140 for o in m.objects),
        native_editor_checked=False,full_playtest=False)
    report.update(validate(m,report))
    report['landings']=audit_landings(m,docks)
    land_routes=[]
    blocked=obstacle_cells(m)
    for r in records:
        v=r['visit']; origin=docks[r['island']] if r['island']!='hades' else (62,8,1)
        route=shortest_route(m,origin,(v[0],v[1]+1,v[2]),blocked=blocked,land_only=True,diagonal=False)
        land_routes.append(dict(island=r['island'],label=r['label'],steps=len(route)-1))
    report['shore_access']=dict(routes=land_routes,max_steps=max(r['steps'] for r in land_routes),
        model='Cardinal land-only paths from beach to each southern approach, with final scenery.')
    legs=[(a+' → '+b,(*docks[a][:1],docks[a][1]+4,0),(*docks[b][:1],docks[b][1]+4,0))
          for a,b in zip(SEA_ORDER,SEA_ORDER[1:])]
    report['pacing']=audit_sea_legs(m,legs,max_steps=30)
    old_docks=harbours(previous_map,OLD_ISLANDS)
    old_legs=[(a+' → '+b,(old_docks[a][0],old_docks[a][1]+4,0),(old_docks[b][0],old_docks[b][1]+4,0))
              for a,b in zip(SEA_ORDER,SEA_ORDER[1:])]
    report['pacing_previous']=audit_sea_legs(previous_map,old_legs)
    return m,report
