"""Revision 7: rewards that prepare a later battle, ambushes and a real finale."""
from copy import deepcopy
from dataclasses import replace

from h3m import catalog, conditions
from h3m.adventure import Reward, read_reward, timed_message
from h3m.authored import hero, monster, seer, quest
from h3m.build import sign_payload
from h3m.pacing import obstacle_cells, shortest_route, audit_landings, audit_sea_legs
from h3m.town_growth import growth_town
from odyssey.labyrinth import generate as landscape
from odyssey.playable import validate


FORK_SEGMENTS=(((68,52),(71,52)),((71,52),(71,58)),((71,58),(68,58)))
TASKS={
 'troy':'Дозор захватил ахейский топор. Отбейте оружие: оно поможет против киконов. В лагере есть обучение нападению.',
 'ismar':'Киконы охраняют клинок и захваченные припасы. Возьмите награду в бою. У выхода из бухты вода подозрительно тихая.',
 'lotus':'Разбойники захватили разведчиков. Победа даст лук; спасённые солдаты остаются с вами. В лесу можно изучить Меткость.',
 'cyclops':'Полифем хранит Глаз циклопа — Кулон ясновидения. Подготовьтесь в лагере и одолейте его. Кулон защитит от ослепления; у Эола водятся единороги.',
 'aeolus':'Эол одолжит Сферу небесного свода. Изучите Молнию у корабля: сфера усилит её в боях с ветрами. За мысом есть испытание единорогов.',
 'lights':'Ветры вырвались из меха. Победите их, заберите награду и возвращайтесь к Эолу. Сфера остаётся с вами до Калипсо.',
 'giants':'Циклопы-лестригоны хранят Тунику короля циклопов. Заберите её: сила магии пригодится в царстве теней. В боковом гроте можно спасти воинов.',
 'circe':'Гермес даёт молю — Кулон свободной воли. Наденьте его перед встречей с гипнотизирующими чудовищами в подземелье. В роще ждут припасы и обучение.',
 'hades':'Чудовища преградили путь к Тиресию. Молю защищает от их гипноза. После боя прорицатель даст Кулон отрицания: он пригодится против грозовых птиц.',
 'sirens':'Большой отряд нимф перекрыл пролив и захватил щит. Победите их ради защиты для следующего испытания. В боковой бухте — ахейская казна.',
 'scylla':'За бухтой два прохода. Восточный стерегут быстрые аспиды: опасны яд и ответный удар. Западный — гидры: не окружайте их пехотой. Достаточно одного пути; награды различаются.',
 'helios':'Стадо Гелиоса охраняет доспехи и провизию. Победа позволит подготовиться к последней буре. Не спешите: на берегу есть обучение защите.',
 'calypso':'Страж берега удерживает материалы для отплытия. Победа откроет путь. Калипсо обменяет испытанную в странствиях сферу на Плащ скорости — если он полезнее вашему войску.',
 'phaeacia':'Состязания Алкиноя открывают Итаку и дают доспехи. Два мастера предлагают обменять Глаз циклопа: на Золотой лук для стрелков либо Ожерелье небесного блаженства. Выберите одно.',
 'ithaca':'Антиной, синий герой, захватил дворец. Его город растит войска каждую неделю. Победа над Антиноем завершит возвращение Одиссея.',
}


def generate(assets,seed=20260905):
    m,r=landscape(assets,seed,extra_segments=FORK_SEGMENTS)
    r['gameplay_revision']=7
    r['objectives']=dict(TASKS)
    docks={h['island']:tuple(h['beach']) for h in r['landings']['harbours']}
    land={x['key']:set(map(tuple,x['protected_cells'])) for x in r['layout']}
    def visit(o):
        dx,dy=m.object_templates[o.template_index].visitable_cells()[0]
        return o.x+dx,o.y+dy,o.z
    def footprint(o):
        return {(o.x+dx,o.y+dy,o.z) for dx,dy in m.object_templates[o.template_index].blocked_cells()}
    def erase(o):
        m.objects.remove(o)
        r['action_sites'][:]=[a for a in r['action_sites'] if not(a['object_id']==o.object_id and tuple(a['position'])==o.position)]
    for o in list(m.objects):
        if o.object_id==83:erase(o)
    r.update(quests=[],chapters=[],bargains=[],optional_quest_positions=[],training=[],ambushes=[])

    def put(kind,key,target,payload=b'',sub=0,*,water=False,near=False,label=''):
        t=assets.get(kind,sub)
        if water:t=replace(t,terrain_mask=t.terrain_mask|256)
        dx,dy=t.visitable_cells()[0]
        candidates=[target]
        if near:
            x,y,z=target
            candidates=sorted(land[key],key=lambda c:(abs(c[0]-x)+abs(c[1]-y),c))
        for c in candidates:
            ax,ay,z=c[0]-dx,c[1]-dy,c[2]
            cells={(ax+x,ay+y,z) for x,y in set(t.blocked_cells())|set(t.visitable_cells())}
            if not all(0<=x<72 and 0<=y<72 for x,y,z in cells):continue
            if not water and not cells<=land[key]:continue
            overlaps=[o for o in m.objects if footprint(o)&cells]
            if any(not 114<=o.object_id<=161 or not footprint(o)<=land.get(key,set()) for o in overlaps):continue
            for o in overlaps:m.objects.remove(o)
            catalog.place(m,catalog.BorrowedObject(t,payload,'reward journey'),ax,ay,z)
            obj=m.objects[-1]
            if not water:
                try:
                    solid=obstacle_cells(m)
                    # Existing interactions must survive the new footprint.
                    for a in [*r['action_sites'],dict(island=key,visit=c)]:
                        if a['island']!=key:continue
                        origin=tuple(a.get('origin',docks.get(key,(62,8,1))))
                        v=a['visit'];route=shortest_route(m,origin,(v[0],v[1]+1,v[2]),blocked=solid,land_only=True,diagonal=False)
                        if len(route)-1>12:raise ValueError('Training detour exceeds shore travel budget')
                except ValueError:
                    m.objects.remove(obj);m.objects.extend(overlaps);continue
                r['action_sites'].append(dict(island=key,label=label or str(kind),object_id=kind,position=list(obj.position),visit=list(c)))
            return obj
        raise ValueError(f'No safe reward placement: {kind}/{sub} {key} {target}')

    def battle(key,cell,creature,count,uid,item=65535,gold=0,*,water=False,message=''):
        o=put(54,key,cell,monster(uid,count,message,item,resources=(0,0,0,0,0,0,gold)),creature,water=water,near=not water,label=message)
        row=dict(island=key,identifier=uid,position=list(o.position),creature=creature,count=count,artifact=item,gold=gold)
        r['encounters'].append(row)
        if water:r['sea_encounters'].append(row)
        return o

    def hut(key,cell,item,mission,required,text,done,*,reward_kind=8):
        o=put(83,key,cell,seer(required,item,text,done,mission=mission,reward_kind=reward_kind),near=True,label=text)
        row=dict(island=key,position=list(o.position),reward=item,mission=mission,required=required,first=text,done=done,reward_kind=reward_kind)
        r['quests'].append(row);r['optional_quest_positions'].append(list(o.position))
        return o

    # Immediate rewards from actual monster defeats; never a second errand.
    loot={50000:(7,600),30040:(8,1200),50001:(60,1000),30042:(28,2000),
          30044:(31,2500),50002:(34,2000),40000:(65535,800),40001:(65535,1200),
          40002:(16,1500),40003:(65535,1000),40004:(65535,1000),40005:(65535,1200),
          40006:(65535,800),60000:(37,1800)}
    for b in list(r['encounters']):
        o=next(o for o in m.objects if o.object_id==54 and list(o.position)==b['position'])
        if b['identifier']==30045:
            erase(o);r['encounters'].remove(b);continue
        item,gold=loot[b['identifier']]
        if b['identifier']==40002:b['count']=160
        o.payload=monster(b['identifier'],b['count'],TASKS[b['island']]+f' Победа принесёт {gold} золота'+(' и артефакт.' if item!=65535 else '.'),item,resources=(0,0,0,0,0,0,gold))
        b.update(artifact=item,gold=gold)
    battle('cyclops',(6,8,0),95,6,70010,101,1000,message='Глаз Полифема. Победа даст Кулон ясновидения — защиту от ослепления.')
    battle('hades',(62,9,1),168,8,70014,65535,1800,message='Чудовища гипнотизируют спутников. Надетое молю — Кулон свободной воли — защищает от их чар.')
    battle('calypso',(42,62,0),115,32,70019,19,1500,message='Страж удерживает чертёж плота и Шлем белого единорога. Освободите путь к феакам.')
    hut('aeolus',(24,8,0),79,8,(0,),TASKS['aeolus'],'Сфера усиливает Молнию. Не отдавайте её в проливе: она пригодится в долгом пути.')
    hut('circe',(60,8,0),105,8,(0,),TASKS['circe'],'Молю у вас. Наденьте кулон перед спуском к Тиресию.')
    hut('hades',(60,10,1),106,4,(70014,),TASKS['hades'],'Кулон отрицания защитит от молний грозовых птиц. Отправляйтесь к сиренам.')
    hut('calypso',(42,60,0),99,5,(79,),TASKS['calypso'],'Сфера возвращается богам. Плащ ускорит ваших бойцов в последних битвах.')
    hut('phaeacia',(24,60,0),91,5,(101,),'Мастер лука: отдать Глаз циклопа за Золотой лук? Он убирает штраф дальности у стрелков. У соседа — другое предложение.','Золотой лук готов. Испытайте его на состязаниях и против женихов.')
    hut('phaeacia',(24,64,0),35,5,(101,),'Мастер амулетов: отдать Глаз циклопа за Ожерелье небесного блаженства? Оно усилит все основные характеристики. Обмен исключает получение Золотого лука.','Ожерелье усилит и воинов, и магию. Глаз циклопа передан мастеру.')
    # Optional purchases spend battle loot on lasting strength, never on access.
    for key,cell,cost,reward,kind,text in (
        ('ismar',(6,42,0),1000,(3,8),10,'Восемь арбалетчиков за 1000 золота из трофеев киконов. Найм необязателен.'),
        ('giants',(42,6,0),1500,(0,2),6,'Ветеран обучит нападению (+2) за 1500 золота. Сюжет можно продолжить без оплаты.'),
        ('helios',(60,60,0),1800,(1,2),6,'Мастер щита обучит защите (+2) за 1800 золота. Подготовка к финалу, не плата за проход.')):
        hut(key,cell,reward,7,(0,0,0,0,0,0,cost),text,'Подготовка завершена. Используйте награду в дальнейших боях.',reward_kind=kind)
    gate_changes={'aeolus':(4,(70010,)),'lights':(4,(40000,)),'giants':(4,(60000,)),
                  'hades':(8,(0,)),'sirens':(4,(70014,)),'helios':(8,(0,)),'phaeacia':(4,(70019,))}
    for g in r['harbour_guards']:
        if g['island'] in gate_changes:g['mission'],g['required']=gate_changes[g['island']]
        o=next(o for o in m.objects if o.object_id==215 and list(o.position)==g['position'])
        o.payload=quest(g['required'],'Завершите испытание предыдущей бухты. Проход не требует сдачи артефактов или войск.',TASKS[g['island']],mission=g['mission'])

    # Refresh old supply sites; supplies are tools and rewards, not instant tolls.
    for c in r['choices']:
        o=next(o for o in m.objects if o.object_id==6 and list(o.position)==c['position'])
        d=read_reward(o.payload)
        reward=Reward(d['message'],guards=tuple(d['guards']),army=tuple(d['army']),resources=tuple(d['resources']),
            artifacts=tuple(a for a,_ in d['artifacts']),spells=tuple(d['spells']),experience=d['experience'],mana=d['mana'])
        if c['island']=='cyclops' and not c['optional']:
            reward=Reward('Припасы пещеры: меткие стрелки и Щит гномьих владык помогут выдержать камни Полифема.',army=((3,6),),artifacts=(13,),experience=500)
        elif c['island']=='circe' and c['title'].startswith('Роща'):
            reward=Reward('Охраняемая роща. Победа даст обучение магии воздуха, самоцветы и мечников для дальнейшего пути.',guards=((86,35),(87,16)),army=((6,10),),resources=(0,0,0,0,0,7,0),skills=((15,2),),experience=1500)
        elif c['title']=='Шестеро гребцов':
            reward=Reward('Ветераны присоединяются перед развилкой. Их не требуется никому отдавать.',army=((1,18),),experience=500)
        elif c['title']=='Материалы для плота':
            reward=Reward('Клад в бухте Калипсо. Победа даст ресурсы для найма и прибавку к защите.',guards=((115,24),(153,45)),resources=(10,0,10,0,0,0,2500),primary=(0,1,0,0),experience=1800)
        o.payload=reward.pandora()
        c.update(title=reward.message.split('.')[0],guards=reward.guards,army=reward.army,resources=reward.resources,
                 artifacts=reward.artifacts,spells=reward.spells,experience=reward.experience,primary=reward.primary,skills=reward.skills)
        for a in r['action_sites']:
            if a['object_id']==6 and a['position']==list(o.position):a['label']=c['title']

    # Native attribute sites offer short, visible preparation detours.
    sites=[('troy',51),('ismar',23),('lotus',32),('cyclops',51),('aeolus',61),
           ('giants',23),('circe',32),('sirens',51),('scylla',23),('helios',23),('calypso',61),('phaeacia',4)]
    labels={51:'Лагерь наёмников: нападение',23:'Башня Марлетто: защита',32:'Сад откровения: знание',61:'Звёздная ось: сила магии',4:'Арена: выбор нападения или защиты'}
    centers={i['key']:i['center'] for i in r['islands']}
    for key,kind in sites:
        x,y,z=centers[key];o=put(kind,key,(x-2,y-2,z),near=True,label=labels[kind])
        r['training'].append(dict(island=key,object_id=kind,position=list(o.position),label=labels[kind]))
    reward=Reward('Сад Эола: единороги ослепляют воинов. Глаз циклопа поможет. За победу — +1 защиты и опыт.',guards=((26,10),),primary=(0,1,0,0),experience=1800)
    o=put(6,'aeolus',(28,11,0),reward.pandora(),near=True,label='Испытание Глаза циклопа')
    r['choices'].append(dict(island='aeolus',title='Испытание Глаза циклопа',position=list(o.position),optional=True,guards=reward.guards,army=(),artifacts=(),experience=1800))

    # Invisible native events occupy unavoidable cells in narrow crossings.
    reef=next(t for ts in assets.templates.values() for t in ts if t.object_id in (147,161) and t.blocked_cells()==[(0,0)] and t.allows_terrain(8) and not t.visitable_cells())
    def narrow(cell):
        x,y,z=cell;solid=obstacle_cells(m)
        for xx in range(x-3,x+4):
            c=(xx,y,z)
            if xx==x or not 0<=xx<72 or c in solid or not m.terrain.tile(*c).is_water:continue
            catalog.place(m,catalog.BorrowedObject(reef,b'','battle crossing'),*c)
    for key,cell,guards,reward in (
        ('ismar',(16,56,0),((153,35),(115,10)),dict(resources=(0,0,0,0,0,0,900),primary=(0,1,0,0))),
        ('lights',(34,30,0),((115,22),),dict(resources=(0,0,0,0,0,0,1200),skills=((15,2),))),
        ('sirens',(69,36,0),((97,14),),dict(resources=(0,0,0,0,0,0,1600),primary=(0,0,1,0)))):
        narrow(cell)
        d=Reward('Засада! Из тумана налетают преследователи. Победа принесёт трофеи и боевой опыт.',guards=guards,experience=1200,**reward)
        o=put(26,key,cell,d.event(),water=True)
        r['ambushes'].append(dict(island=key,position=list(o.position),guards=guards))
    # The fork rejoins before Helios. Either fight is enough; both give loot.
    for yy in range(53,55):
        for xx in (68,69):
            if (xx,yy,0) not in obstacle_cells(m):catalog.place(m,catalog.BorrowedObject(reef,b'','fork divider'),xx,yy,0)
    for xx in (65,66,71):
        if m.terrain.tile(xx,54,0).is_water and (xx,54,0) not in obstacle_cells(m):catalog.place(m,catalog.BorrowedObject(reef,b'','fork bank'),xx,54,0)
    for cell,creature,count,uid,item,label in (((70,54,0),166,5,70101,38,'Восточный проход: аспиды'),((67,54,0),110,15,70102,39,'Западный проход: гидры')):
        battle('scylla',cell,creature,count,uid,item,1500,water=True,message=label+'. Победа даст артефакт и откроет этот путь; другой бой необязателен.')
    r['optional_monster_ids']=[70101,70102]
    r['fork']=dict(entry=(68,52,0),exit=(68,58,0),alternatives=[70101,70102])

    # No ceremonial item after the last battle: the native victory is the hero.
    town=next(o for o in m.objects if o.object_id==98 and o.payload[4]==255)
    town.payload=growth_town('Дворец женихов')
    blue=deepcopy(m.players[0]);blue.can_human_play=0;blue.can_computer_play=1
    blue.main_town_pos=visit(town);blue.ai_tactic=2;m.players[1]=blue
    enemy_template=assets.get(34)
    tx,ty,z=visit(town)
    x,y=tx,ty+1
    dx,dy=enemy_template.visitable_cells()[0]
    catalog.place(m,catalog.BorrowedObject(enemy_template,hero(name='Антиной',biography='Предводитель женихов. Собирает войска во дворце, пока Одиссей странствует.',
        owner=1,hero_id=1,identifier=71000,patrol=1,experience=15000,primary=(8,8,4,4),
        army=((7,40),(3,35),(1,40)),artifacts=(),spells=(27,41,53,62),skills=((22,2),(23,2),(1,2),(15,2))), 'final antagonist'),x-dx,y-dy,z)
    enemy=m.objects[-1]
    m.victory=conditions.VictoryCondition(conditions.VictoryType.BEAT_HERO,0,0,bytes((x,y,z)))
    r['finale']=dict(identifier=71000,position=list(enemy.position),visit=[x,y,z],owner=1,town=list(town.position),
        growth=dict(first_day=8,repeat_days=7,extra_archers=8,extra_swordsmen=5,gold=10000,mechanism='Town recruitment pool; AI hires and transfers troops. Native AI behavior requires playtest.'))
    for o in m.objects:
        if o.object_id==91:
            key=min((i for i in r['islands'] if i['center'][2]==o.z),key=lambda i:abs(o.x-i['center'][0])+abs(o.y-i['center'][1]))['key']
            o.payload=sign_payload(TASKS[key].encode('cp1251'))
        elif o.object_id==26 and not any(a['position']==list(o.position) for a in r['ambushes']):
            scene=next(s for s in r['scenes'] if s['position']==list(o.position))
            key=scene['island'];scene['message']=TASKS[key]
            o.payload=Reward(TASKS[key],mana=5,movement=250,spells=(17,) if key=='aeolus' else ()).event()
    m.header.description=('Одиссея: награды и испытания. Засады, обучение на берегах, два прохода Сциллы и Харибды. '
        'Победите синего Антиноя во дворце: это завершит игру. Его город растит войска каждую неделю. '
        'Начните новую игру на 100%.').encode('cp1251')
    m.events.events=[timed_message('Возвращение Одиссея','Отбейте у дозора топор и садитесь в корабль. Награды готовят вас к следующим боям. '
        'Сохраняйте Глаз циклопа и Сферу небесного свода: обмен предложат лишь позднее. '
        'Во дворце Антиной собирает войска; победа над синим героем завершает карту.')]
    r['chapters']=list(r['quests']);r['objects']=len(m.objects)
    r['balance']['counts']={str(b['identifier']):b['count'] for b in r['encounters']}
    r['balance']['final_army']=[(7,40),(3,35),(1,40)]
    r['balance']['assumptions']='Authored rewards and counters; battle losses, duration and AI recruiting need native playtest.'
    r['total_battles']=len(r['encounters'])+sum(bool(c['guards']) for c in r['choices'])+len(r['ambushes'])+1
    r['sea_battles']=len(r['sea_encounters'])+len(r['ambushes'])
    r.update(validate(m,r))
    r['fork']['verified_alternatives']={str(uid):validate(m,r,avoid_battles={uid})['sequential_playthrough_model'] for uid in r['optional_monster_ids']}
    mandatory=deepcopy(m)
    optional={tuple(c['position']) for c in r['choices'] if c['optional']}
    mandatory.objects=[o for o in mandatory.objects if o.object_id!=83 and not(o.object_id==6 and o.position in optional)]
    r['mandatory_without_optional']=validate(mandatory,r)['sequential_playthrough_model']
    r['landings']=audit_landings(m,docks)
    solid=obstacle_cells(m);routes=[]
    for a in r['action_sites']:
        v=a['visit'];origin=tuple(a.get('origin',docks.get(a['island'],(62,8,1))))
        route=shortest_route(m,origin,(v[0],v[1]+1,v[2]),blocked=solid,land_only=True,diagonal=False)
        routes.append(dict(island=a['island'],label=a['label'],steps=len(route)-1))
    r['shore_access']=dict(routes=routes,max_steps=max(a['steps'] for a in routes))
    legs=r['pacing']['legs'];r['pacing']=audit_sea_legs(m,[(a['label'],a['start'],a['end']) for a in legs],max_steps=30)
    return m,r
