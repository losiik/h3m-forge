"""A shore objective for false Ithaca, without another mandatory battle."""
from h3m import catalog
from h3m.adventure import read_monster
from h3m.authored import monster, seer
from h3m.pacing import obstacle_cells, shortest_route, audit_landings, audit_sea_legs

TASK = ('Ветры разбили корабль о берег. Высадитесь и усмирите четыре водных элементаля '
        'у обломков в глубине острова. Победа откроет пролив к лестригонам. '
        'После боя заберите трёх спасённых арбалетчиков в хижине и восстановите ману '
        'у магического колодца. Возвращаться к Эолу не нужно; сфера остаётся с вами до Калипсо.')


def enrich(m, r, assets):
    key = 'lights'
    land = set(map(tuple, next(i['protected_cells'] for i in r['layout'] if i['key']==key)))
    docks = {h['island']:tuple(h['beach']) for h in r['landings']['harbours']}

    def footprint(o):
        return {(o.x+x,o.y+y,o.z) for x,y in m.object_templates[o.template_index].blocked_cells()}

    def routes():
        solid=obstacle_cells(m)
        rows=[]
        for a in r['action_sites']:
            if a['island']!=key:continue
            x,y,z=a['visit']
            path=shortest_route(m,docks[key],(x,y+1,z),blocked=solid,land_only=True,diagonal=False)
            if len(path)-1>12:raise ValueError('Wind island action exceeds shore travel budget')
            rows.append(dict(island=key,label=a['label'],steps=len(path)-1))
        return rows

    def put(kind, target, payload, label, sub=0):
        t=assets.get(kind,sub)
        dx,dy=t.visitable_cells()[0]
        for x,y,z in sorted(land,key=lambda c:(abs(c[0]-target[0])+abs(c[1]-target[1]),c)):
            ax,ay=x-dx,y-dy
            cells={(ax+xx,ay+yy,z) for xx,yy in set(t.blocked_cells())|set(t.visitable_cells())}
            if not cells<=land:continue
            overlaps=[o for o in m.objects if footprint(o)&cells]
            if any(not 114<=o.object_id<=161 or not footprint(o)<=land for o in overlaps):continue
            for o in overlaps:m.objects.remove(o)
            catalog.place(m,catalog.BorrowedObject(t,payload,'wind island shore objective'),ax,ay,z)
            obj=m.objects[-1]
            row=dict(island=key,label=label,object_id=kind,position=list(obj.position),visit=[x,y,z])
            r['action_sites'].append(row)
            try:routes()
            except ValueError:
                r['action_sites'].remove(row);m.objects.remove(obj);m.objects.extend(overlaps)
                continue
            return obj
        raise ValueError(f'No accessible placement for wind island {kind}')

    entry=next(b for b in r['encounters'] if b['identifier']==60000)
    old=next(o for o in m.objects if o.object_id==54 and list(o.position)==entry['position'])
    d=read_monster(old.payload)
    m.objects.remove(old)
    r['sea_encounters']=[b for b in r['sea_encounters'] if b['identifier']!=60000]
    wind=put(54,(26,24),monster(60000,d['count'],TASK,d['artifact'],resources=d['resources'],
                              upgraded_stack=0,stack_count=1),'Усмирить ветры у обломков',115)
    entry['position']=list(wind.position)
    shore_guard=next(o for o in m.objects if o.object_id==54 and read_monster(o.payload)['identifier']==40006)
    guard=read_monster(shore_guard.payload)
    shore_guard.payload=monster(40006,guard['count'],'Нимфы стерегут высадку. '+TASK,
        guard['artifact'],resources=guard['resources'],upgraded_stack=0,stack_count=1)
    first='Трое арбалетчиков укрылись от бури. Усмирите элементалей у обломков корабля, и моряки присоединятся к вам бесплатно.'
    done='Три спасённых арбалетчика присоединяются навсегда. Колодец поможет восстановить ману перед лестригонами. Плывите дальше по открытому проливу.'
    hut=put(83,(29,27),seer((60000,),(3,3),first,done,mission=4,reward_kind=10),'Спасённые моряки')
    r['quests'].append(dict(island=key,position=list(hut.position),reward=(3,3),mission=4,
        required=(60000,),first=first,done=done,reward_kind=10))
    r['optional_quest_positions'].append(list(hut.position))
    well=put(48,(23,26),b'','Магический колодец')
    r['objectives'][key]=TASK
    r['wind_island']=dict(revision=1,monster=60000,position=list(wind.position),
        rescue_hut=list(hut.position),well=list(well.position),reward_army=[(3,3)],
        opens='giants',return_to_aeolus_required=False,added_battles=0)
    r['shore_access']['routes']=[a for a in r['shore_access']['routes'] if a['island']!=key]+routes()
    r['shore_access']['max_steps']=max(a['steps'] for a in r['shore_access']['routes'])
    r['landings']=audit_landings(m,docks)
    legs=r['pacing']['legs']
    r['pacing']=audit_sea_legs(m,[(a['label'],a['start'],a['end']) for a in legs],max_steps=30)
    r['sea_battles']=len(r['sea_encounters'])+len(r['ambushes'])
    r['objects']=len(m.objects)
