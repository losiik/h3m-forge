"""Compile arbitrary chapter graphs into native, checked HotA sea adventures."""
from collections import Counter, deque
from dataclasses import replace
from math import hypot
from random import Random
from types import SimpleNamespace

from h3m import authored as p, catalog, conditions, hota, mapfile, options
from h3m.adventure import Reward, read_reward, read_monster, timed_message
from h3m.build import sign_payload
from h3m.coast import place_barriers
from h3m.pacing import audit_landings, audit_sea_legs, obstacle_cells, shortest_route
from h3m.scenario_spec import ScenarioSpec
from h3m.terrain import Terrain, TerrainMap
from h3m.world import scenery_for

# Compact spiral; graph topology is independent of these authored map slots.
SLOTS = ((8,62),(8,44),(8,26),(8,8),(26,8),(44,8),(62,8),(62,26),
         (62,44),(62,62),(44,62),(26,62),(26,44),(26,26),(44,26),(44,44))


def reward(spec, text, artifacts=()):
    return Reward(text, army=tuple(map(tuple,spec.army)), resources=tuple(spec.resources),
                  artifacts=tuple(spec.artifacts)+tuple(artifacts),spells=tuple(spec.spells),
                  experience=spec.experience,mana=spec.mana)


def reward_summary(r):
    names=('дерево','ртуть','руда','сера','кристаллы','самоцветы','золото')
    parts=[f'{name}: {amount}' for name,amount in zip(names,r.resources) if amount]
    if r.army:parts.append(f'пополнение: {sum(n for _,n in r.army)} бойцов')
    if r.experience:parts.append(f'опыт: {r.experience}')
    if r.mana:parts.append(f'мана: {r.mana}')
    if r.spells:parts.append(f'заклинания: {len(r.spells)}')
    if r.artifacts:parts.append(f'артефакты: {len(r.artifacts)}')
    return '; '.join(parts) or 'сюжетная встреча'


class Builder:
    def __init__(self,m,assets):
        self.m,self.assets=m,assets
        self.occupied=set(); self.reserved=set(); self.actions=[]

    def place(self,kind,cell,payload=b'',sub=0,*,near=False,water=False,record=None):
        soil=self.m.terrain.tile(*cell).terrain
        t=self.assets.get(kind,sub,terrain=None if water or kind in (26,54,215,34,98) else soil)
        if water:t=replace(t,terrain_mask=t.terrain_mask | 256)
        offsets=t.visitable_cells()
        dx,dy=offsets[0] if offsets else (0,0)
        candidates=[cell]
        if near:
            candidates=sorted(((cell[0]+x,cell[1]+y,0) for x in range(-4,5) for y in range(-4,5)),
                              key=lambda c:(abs(c[0]-cell[0])+abs(c[1]-cell[1]),c))
        for visit in candidates:
            anchor=(visit[0]-dx,visit[1]-dy,visit[2])
            cells={(anchor[0]+x,anchor[1]+y,anchor[2]) for x,y in set(t.blocked_cells())|set(offsets)}
            solids={(anchor[0]+x,anchor[1]+y,anchor[2]) for x,y in t.blocked_cells() if (x,y) not in offsets}
            if cells & self.occupied or solids & self.reserved:continue
            if any(not(0<=x<72 and 0<=y<72) or self.m.terrain.tile(x,y,z).is_water!=water for x,y,z in cells):continue
            if record and (visit[0],visit[1]+1,visit[2]) in self.occupied:continue
            if not all(0<=a<72 for a in anchor[:2]):continue
            catalog.place(self.m,catalog.BorrowedObject(t,payload,'scenario compiler'),*anchor)
            o=self.m.objects[-1];self.occupied.update(cells)
            if record:
                approach=(visit[0],visit[1]+1,visit[2]); self.reserved.add(approach)
                self.actions.append(dict(chapter=record[0],label=record[1],visit=visit,approach=approach))
            return o
        raise ValueError(f'Cannot place {kind}/{sub} at {cell}; reduce chapter contents')

    def stone(self,cell):
        soil=self.m.terrain.tile(*cell).terrain
        ts=[t for group in self.assets.templates.values() for t in group
            if t.object_id in (116,119,130,133,134,135,136,137,140) and t.allows_terrain(soil)
            and len(t.blocked_cells())==1 and not t.visitable_cells()
            and t.animation_file.lower().startswith((b'avlr',b'avlo',b'avlm',b'avld',b'avlsn',b'avlsptr',b'avlca',b'avlhpn'))]
        for t in sorted(ts,key=lambda t:t.animation_file):
            dx,dy=t.blocked_cells()[0]; anchor=(cell[0]-dx,cell[1]-dy,cell[2])
            if not all(0<=v<72 for v in anchor[:2]):continue
            if cell in self.occupied:raise ValueError('Completion enclosure overlaps an object')
            catalog.place(self.m,catalog.BorrowedObject(t,b'','completion enclosure'),*anchor)
            self.occupied.add(cell);return
        raise ValueError(f'No native single-cell blocker for {soil}')


def bearings(a,b):
    dx=b[0]-a[0]; dy=b[1]-a[1]
    horizontal='вправо' if dx>0 else 'влево'
    vertical='вниз' if dy>0 else 'вверх'
    return vertical if not dx else horizontal if not dy else vertical+' и '+horizontal


def generate_scenario(spec,assets):
    spec.validate()
    units=list(spec.army)
    for c in spec.chapters:
        units+=c.reward.army+c.challenge.army+c.sea_battle
        if c.challenge.kind=='battle':units.append([c.challenge.creature,c.challenge.count])
        for op in c.opportunities:units+=op.guards+op.reward.army
    for creature in {creature for creature,count in units}:assets.get(54,creature)
    chapters={c.id:c for c in spec.chapters}
    order=spec.order
    m=hota.new_map(spec.name,spec.description,size=72,players=1,seed=spec.seed)
    player=m.players[0];player.can_computer_play=0;player.allowed_factions=1;player.is_faction_random=0
    m.meta.allowed_heroes=options.SizedMask(bytes(27),215)
    m.meta.allowed_spells=bytes([255])*9
    centers=dict(zip(order,SLOTS)); docks={k:(x,y+5,0) for k,(x,y) in centers.items()}
    islands=[SimpleNamespace(key=k,name=chapters[k].title,x=x,y=y,z=0)
             for k,(x,y) in centers.items()]
    data=bytearray(bytes([8,0,0,0,0,0,0])*72*72); lands={}
    for i in islands:
        land=set()
        for y in range(i.y-6,i.y+6,2):
            for x in range(i.x-6,i.x+6,2):
                if hypot(x+1-i.x,y+1-i.y)>6:continue
                for yy in (y,y+1):
                    for xx in (x,x+1):
                        data[(yy*72+xx)*7]=Terrain[chapters[i.key].terrain.upper()];land.add((xx,yy,0))
        lands[i.key]=land
    m.terrain=TerrainMap(bytes(data),72,1);assets.terrain.apply(m.terrain,seed=spec.seed)
    b=Builder(m,assets)
    for key,(x,y,z) in docks.items(): b.reserved.update((x,yy,z) for yy in range(y-6,y+1))
    used={a for c in spec.chapters for a in c.reward.artifacts+c.challenge.artifacts}
    used.update(a for c in spec.chapters for o in c.opportunities for a in o.reward.artifacts)
    pool=[a for a in range(10,36) if a not in used]
    edges=[(parent,key) for key in order for parent in chapters[key].requires]
    if len(edges)>len(pool):raise ValueError('Too many chapter links for unique native story seals')
    tokens=dict(zip(edges,pool))
    victory=36
    if victory in used:raise ValueError('Artifact 36 is reserved for the finale')
    m.victory=conditions.VictoryCondition(conditions.VictoryType.ARTIFACT,1,0,p.pack('H',victory))
    def local(key,x,y):return centers[key][0]+x,centers[key][1]+y,0
    def onward(key):
        targets=[k for k in order if key in chapters[k].requires]
        if not targets:return 'Это завершение приключения.' if key==spec.finale else 'Вернитесь к основному маршруту.'
        return '\n'.join(f'{order.index(k)+1:02}. {chapters[k].title}: {bearings(centers[key],centers[k])}; '
            f'{"необязательная ветка" if chapters[k].optional else "основной маршрут"}. Вход с юга (снизу).'
            +(f' Сначала завершите также: {", ".join(chapters[p].title for p in chapters[k].requires if p!=key)}.'
              if len(chapters[k].requires)>1 else '') for k in targets)
    gates=[]; completions=[]; battles=[]; supplies=[]; opportunities=[]; reef=set(); lanes=set()
    for key in order:
        c=chapters[key];cx,cy=centers[key];x,y,z=docks[key]
        title=f'{order.index(key)+1:02}. {c.title}'
        brief=(f'ВЫ ЗДЕСЬ: {title}\n\n{c.text}\n\nСЕЙЧАС: {c.challenge.text}\n'
               'Затем пройдите к указателю завершения в ограждённой площадке на севере острова.\n\nДАЛЕЕ:\n'+onward(key))
        ring1={(xx+dx,yy+dy,0) for xx,yy,_ in lands[key] for dx in range(-1,2) for dy in range(-1,2)}
        ring2={(xx+dx,yy+dy,0) for xx,yy,_ in lands[key] for dx in range(-2,3) for dy in range(-2,3)}
        reef.update(c for c in ring2-ring1 if 0<=c[0]<72 and 0<=c[1]<72)
        reef.update((xx,yy,0) for xx in (x-1,x+1) for yy in range(y+1,y+4))
        lanes.update((x,yy,0) for yy in range(y+1,y+5))
        if c.requires:
            req=[tokens[parent,key] for parent in c.requires]
            text=f'{title}\nСначала завершите: '+', '.join(chapters[parent].title for parent in c.requires)+'.'
            o=b.place(215,(x,y+3,0),p.quest(req,text,'Путь открыт.\n'+brief),water=True)
            gates.append(dict(chapter=key,role='entry',position=o.position))
        if c.sea_battle:
            creature,count=c.sea_battle[0];ident=40000+order.index(key)
            o=b.place(54,(x,y+1,0),p.monster(ident,count,'Морское испытание перед '+c.title,65535),creature,water=True)
            battles.append(dict(chapter=key,position=o.position,identifier=ident))
        if key!=order[0]:b.place(26,(x,y+2,0),Reward(brief,movement=500,mana=10).event(),water=True)
        # A three-cell-wide rock alcove: only the southern gate reaches its event.
        for dx in (-1,1):
            for dy in (-3,-2,-1):b.stone(local(key,dx,dy))
        for dx in (-1,0,1):b.stone(local(key,dx,-4))
        marker=b.place(91,local(key,0,-3),sign_payload(('ЗАВЕРШЕНИЕ: '+title+'\n'+onward(key)).encode('cp1251')))
        condition=c.challenge
        mission={'visit':8,'battle':4,'resources':7,'army':6,'artifacts':5}[condition.kind]
        req={'visit':[0],'resources':condition.resources,'army':condition.army,'artifacts':condition.artifacts}.get(condition.kind)
        if condition.kind=='battle':
            ident=30000+order.index(key);req=[ident]
            o=b.place(54,local(key,3,0),p.monster(ident,condition.count,condition.text+'\nПосле победы идите к северному указателю.',65535),condition.creature,near=True,record=(key,'Основной бой'))
            battles.append(dict(chapter=key,position=o.position,identifier=ident))
        o=b.place(215,local(key,0,-1),p.quest(req,condition.text,'Испытание пройдено. Шагните к указателю завершения.',mission=mission))
        gates.append(dict(chapter=key,role='completion',position=o.position))
        outgoing=[tokens[e] for e in edges if e[0]==key]+([victory] if key==spec.finale else [])
        completion=reward(c.reward,f'ЗАВЕРШЕНО: {title}\n\n{onward(key)}\n'
                          'Путевые знаки откроют следующие проходы; не продавайте их.',outgoing)
        o=b.place(26,local(key,0,-2),completion.event())
        completions.append(dict(chapter=key,position=o.position,artifacts=outgoing,optional=c.optional))
        # Supplies are available before paying a consumptive chapter condition.
        if condition.auto_supply and condition.kind in ('resources','army','artifacts'):
            supply=Reward('Припасы для задания: '+condition.text,
                resources=tuple(condition.resources),army=tuple(map(tuple,condition.army)),artifacts=tuple(condition.artifacts))
            o=b.place(6,local(key,3,2),supply.pandora(),near=True,record=(key,'Обязательные припасы'))
            supplies.append(dict(chapter=key,position=o.position))
        for index,op in enumerate(c.opportunities):
            rr=replace(reward(op.reward,'НЕОБЯЗАТЕЛЬНО: '+op.title+'\n'+op.text+
                f'\nВсего противников: {sum(n for _,n in op.guards)}. Можно отказаться.\nНаграда: '+reward_summary(op.reward)),guards=tuple(map(tuple,op.guards)))
            o=b.place(6,local(key,-3,1+index*2),rr.pandora(),near=True,record=(key,op.title))
            opportunities.append(dict(chapter=key,position=o.position,title=op.title))
        b.place(91,local(key,-1,3),sign_payload(brief.encode('cp1251')),near=True,record=(key,'Указатель'))
        if key!=order[0]:b.place(59,(x+1,y+4,0),sign_payload((title+'\n'+brief).encode('cp1251')),water=True)
    root=order[0]
    town=b.place(98,local(root,-3,0),p.town('Лагерь: '+spec.hero_name,0),near=True,record=(root,'Город'))
    player.has_main_town=1;player.main_town_pos=(town.x-2,town.y,town.z)
    player.generate_hero_at_main_town=0
    hero=b.place(34,local(root,0,2),p.hero(name=spec.hero_name,biography=spec.hero_biography,
        army=tuple(map(tuple,spec.army)),artifacts=(),spells=tuple(spec.spells),
        skills=tuple(map(tuple,spec.hero_skills)),equipped={0:136}),near=True)
    t=m.object_templates[hero.template_index];dx,dy=t.visitable_cells()[0];start=(hero.x+dx,hero.y+dy,0)
    m.loss=conditions.LossCondition(conditions.LossType.LOSE_HERO,bytes(start))
    x,y,_=docks[root];b.place(8,(x,y+1,0),water=True)
    hut=b.place(37,local(root,-3,4),near=True,record=(root,'Обзор архипелага'))
    for key in order[1:]: b.place(27,local(key,3,-3),near=True)
    themes={}
    for c in spec.chapters:
        soil=Terrain[c.terrain.upper()]
        ids=(134,140,130) if soil==Terrain.SAND else (135,137,140) if soil in (Terrain.GRASS,Terrain.SWAMP) else (134,136,140)
        if soil==Terrain.LAVA:ids=(134,127,128,119,130,140)
        if soil==Terrain.SNOW:ids=(134,137,140,130)
        themes[c.id]=(c.title,soil,ids)
    reef.difference_update(lanes)
    barrier=place_barriers(m,assets,islands,reef,lanes,b.occupied,spec.seed,themes)
    permanent=obstacle_cells(m); routes=[]
    for action in b.actions:
        path=shortest_route(m,docks[action['chapter']],action['approach'],blocked=permanent,land_only=True,diagonal=False)
        if len(path)-1>14:raise ValueError('An island action is too far from its beach')
        b.reserved.update(path);routes.append(dict(action,steps=len(path)-1))
    rng=Random(spec.seed)
    all_land=set.union(*lands.values())
    for cell in sorted(all_land):
        if cell in b.occupied|b.reserved or rng.random()>spec.decoration_density:continue
        palette=scenery_for(assets,m.terrain.tile(*cell).terrain);rng.shuffle(palette)
        for t in palette:
            footprint={(cell[0]+dx,cell[1]+dy,0) for dx,dy in set(t.blocked_cells())|{(0,0)}}
            if not footprint<=all_land or footprint & (b.occupied|b.reserved):continue
            catalog.place(m,catalog.BorrowedObject(t,b'','scenario scenery'),*cell);b.occupied.update(footprint);break
    m.events.events=[timed_message('Ваше приключение',spec.name+'\n\n'+spec.description+
        '\n\nНачните с: '+chapters[root].title+'. '+chapters[root].challenge.text+
        '\nПосле задания пройдите к указателю в северной ограждённой площадке. '
        'Хижина мага у стартового пляжа открывает обзор островов. У каждого пляжа есть повторно читаемый указатель. '
        'Все пристани — снизу островов. Шляпу адмирала не снимайте. Необязательные бои и ветки можно пропускать.')]
    report=dict(generator='scenario',revision=1,specification=spec.to_dict(),start=start,
        chapters=[dict(id=k,title=chapters[k].title,center=centers[k],land=sorted(lands[k]),optional=chapters[k].optional) for k in order],
        gates=gates,completions=completions,battles=battles,supplies=supplies,opportunities=opportunities,
        tokens=[dict(parent=a,child=z,artifact=v) for (a,z),v in tokens.items()],
        scouting_hut=hut.position,barriers=barrier,actions=routes,objects=len(m.objects))
    report['landings']=audit_landings(m,docks)
    report['pacing']=audit_sea_legs(m,[(a+' → '+z,(docks[a][0],docks[a][1]+4,0),(docks[z][0],docks[z][1]+4,0)) for a,z in edges],max_steps=spec.max_travel)
    if spec.balance_profile == 'fixed':
        from h3m.balance import apply_fixed_profile
        report['balance'] = apply_fixed_profile(m)
    else:
        report['balance'] = dict(profile='standard', native_combat_verified=False)
    from h3m.scenario_audit import audit_scenario
    report['validation']=audit_scenario(m,report)
    return m,report
