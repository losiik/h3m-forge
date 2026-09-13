"""Revision 12: an optional guarded mana well at Scylla's fork."""
from collections import deque
from copy import deepcopy
from dataclasses import replace

from h3m import catalog
from h3m.adventure import Reward, read_reward
from h3m.authored import hero
from h3m.build import sign_payload
from h3m.objtypes import Obj
from h3m.pacing import obstacle_cells, shortest_route, audit_landings
from h3m.terrain import Terrain
from h3m.skills import SecondarySkill
from odyssey.barriers import natural_cap_template
from odyssey.playable import validate
from odyssey.sirens_journey import generate as previous
from odyssey.small_company import _reward
from odyssey.siege_journey import FINAL_ARMY

# VCMI config/creatures/neutral.json: Rogue=143, Nomad=142.
WELL_GUARDS = ((143,30),(142,15))
ANTINOUS_PRIMARY = (12,12,5,4)
ANTINOUS_SPELLS = (27,35,41,53,54)  # Resurrection (38) deliberately absent.
TASK = ('Два прохода между скалами: быстрые аспиды на востоке, гидры на западе. '
        'Выберите, чем рискнуть. На острове воры и кочевники захватили магический колодец.')


def well_access(m, beach, visit, guard):
    """Prove no adjacent interaction before battle, even with corner cutting.

    Land-only flood fill deliberately allows every diagonal. This is more
    permissive than native walking; it does not rely on monster attack zones.
    """
    solid=obstacle_cells(m)
    def flood(closed):
        seen={tuple(beach)};queue=deque(seen)
        while queue:
            x,y,z=queue.popleft()
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    cell=(x+dx,y+dy,z)
                    if cell in seen or cell in closed or not (0<=cell[0]<m.header.size and 0<=cell[1]<m.header.size):continue
                    if m.terrain.tile(*cell).terrain in (8,9):continue
                    seen.add(cell);queue.append(cell)
        return seen
    x,y,z=visit
    interactions={(x+dx,y+dy,z) for dx in (-1,0,1) for dy in (-1,0,1)}
    if flood(solid|{tuple(guard)})&interactions:
        raise ValueError('Mana well can be visited without defeating its guard')
    approach=(x,y+1,z)
    if approach not in flood(solid):raise ValueError('Mana well remains inaccessible after battle')
    route=shortest_route(m,beach,approach,blocked=solid,land_only=True,diagonal=False)
    if len(route)-1>12:raise ValueError('Mana well exceeds shore travel budget')
    return dict(no_bypass=True,accessible_after_battle=True,steps=len(route)-1,
                model='Eight-direction land movement with corner cutting; all adjacent well interactions tested.')


def _add_well(m,r,assets):
    land=set(map(tuple,next(i['protected_cells'] for i in r['layout'] if i['key']=='scylla')))
    beach=tuple(next(h['beach'] for h in r['landings']['harbours'] if h['island']=='scylla'))
    # Use the actual rough-terrain well, not MAGIC_SPRING (48, double mana).
    well=next(t for t in assets.templates[(Obj.MAGIC_WELL,0)] if t.animation_file.lower()==b'avxwelr0.def')
    if well.blocked_cells()!=[(0,0)] or well.visitable_cells()!=[(0,0)]:raise ValueError('Unexpected native well mask')
    event=assets.get(26)
    rocks=sorted((t for t in assets.decorations if t.blocked_cells()==[(0,0)]
        and not t.visitable_cells() and t.allows_terrain(Terrain.ROUGH)
        and natural_cap_template(t,Terrain.ROUGH)),key=lambda t:t.animation_file)
    if not rocks:raise ValueError('No native rocks for the guarded well')
    def footprint(o):
        t=m.object_templates[o.template_index]
        return {(o.x+dx,o.y+dy,o.z) for dx,dy in set(t.blocked_cells())|set(t.visitable_cells())}
    reward=Reward('Воры прячутся за камнями, а кочевники перегораживают тропу к колодцу. '
                  'Чтобы добраться до воды, придётся выбить их из укрытия.',guards=WELL_GUARDS)
    for visit in sorted(land,key=lambda c:(abs(c[0]-63)+abs(c[1]-43),c)):
        x,y,z=visit;guard=(x,y+2,z)
        pocket={(x+dx,y+dy,z) for dx in (-1,0,1) for dy in (-1,0,1,2)}
        if not pocket<=land or beach in pocket:continue
        overlaps=[o for o in m.objects if footprint(o)&pocket]
        if any(not 114<=o.object_id<=161 or not footprint(o)<=land for o in overlaps):continue
        original=list(m.objects)
        m.objects[:]=[o for o in m.objects if o not in overlaps]
        catalog.place(m,catalog.BorrowedObject(well,b'','Scylla mana well'),*visit)
        catalog.place(m,catalog.BorrowedObject(event,reward.event(),'Bandits guarding the well'),*guard)
        wall=sorted(pocket-{visit,(x,y+1,z),guard})
        for i,cell in enumerate(wall):
            catalog.place(m,catalog.BorrowedObject(rocks[i%len(rocks)],b'','Well rock enclosure'),*cell)
        actions=[dict(island='scylla',label='Магический колодец',object_id=49,position=list(visit),visit=list(visit)),
                 dict(island='scylla',label='Воры и кочевники у колодца',object_id=26,position=list(guard),visit=list(guard))]
        try:
            access=well_access(m,beach,visit,guard)
            for a in [*r['action_sites'],*actions]:
                if a['island']!='scylla':continue
                ax,ay,az=a['visit']
                if len(shortest_route(m,beach,(ax,ay+1,az),blocked=obstacle_cells(m),land_only=True,diagonal=False))-1>12:
                    raise ValueError('Well blocks another island interaction')
        except ValueError:
            m.objects[:]=original
            continue
        r['action_sites'].extend(actions)
        return dict(island='scylla',position=list(visit),object_id=49,animation=well.animation_file.decode(),
            guard_position=list(guard),guards=WELL_GUARDS,wall_cells=wall,optional=True,
            reward='Access to a native Magic Well; ordinary mana restoration, not double mana.',
            renewable=True,battle_once=True,access=access,native_gameplay_verified=False)
    raise ValueError('No guarded and accessible Scylla well placement')


def generate(assets,seed=20260905):
    m,r=previous(assets,seed)
    r['gameplay_revision']=12
    enemy=next(o for o in m.objects if o.object_id==34 and o.payload[4]==1)
    enemy.payload=hero(name='Антиной',biography='Предводитель женихов. Созывает стрелков во дворец.',
        owner=1,hero_id=1,identifier=71000,patrol=1,experience=25000,primary=ANTINOUS_PRIMARY,
        army=FINAL_ARMY,artifacts=(),spells=ANTINOUS_SPELLS,
        skills=((22,3),(23,3),(1,3),(SecondarySkill.EARTH_MAGIC,3),(SecondarySkill.AIR_MAGIC,2)))
    r['finale']['hero_balance']=dict(primary=ANTINOUS_PRIMARY,previous_primary=(14,14,6,5),
        spells=ANTINOUS_SPELLS,removed_spells=[38],resurrection=False,native_combat_verified=False)
    r['well_trial']=_add_well(m,r,assets)
    r['objectives']['scylla']=TASK
    for scene in r['scenes']:
        if scene['island']=='scylla':
            obj=next(o for o in m.objects if o.object_id==26 and list(o.position)==scene['position'])
            obj.payload=replace(_reward(read_reward(obj.payload,event=True)),message=TASK).event()
            scene['message']=TASK
    for a in r['action_sites']:
        if a['island']=='scylla' and a['object_id']==91:
            obj=next(o for o in m.objects if o.object_id==91 and list(o.position)==a['position'])
            obj.payload=sign_payload(('За скалами — магический колодец. Воры и кочевники держат единственную тропу. '
                'Отбейте воду, если перед проливом нужно восстановить ману.').encode('cp1251'))
    r['total_battles']+=1
    r['objects']=len(m.objects)
    r['reward_policy']['guarded_renewable_mana_wells']=1
    m.header.description=('Одиссея, редакция 12. У Сциллы и Харибды можно отбить магический колодец у воров и кочевников. '
        'После сирен — 5 древних чудищ. Чаша тишины, мастерская у Трои, меч Эола и возвращение к растущей армии Антиноя.').encode('cp1251')
    r.update(validate(m,r))
    guard=tuple(r['well_trial']['guard_position'])
    r['well_trial']['optional_verified']=validate(m,r,avoid_ambushes={guard})['sequential_playthrough_model']
    optional={tuple(c['position']) for c in r['choices'] if c['optional']}
    mandatory=deepcopy(m)
    mandatory.objects=[o for o in mandatory.objects if o.object_id!=83 and not(o.object_id==6 and o.position in optional)]
    r['mandatory_without_optional']=validate(mandatory,r,avoid_ambushes={guard})['sequential_playthrough_model']
    r['fork']['verified_alternatives']={str(uid):validate(m,r,avoid_battles={uid})['sequential_playthrough_model'] for uid in r['optional_monster_ids']}
    docks={h['island']:tuple(h['beach']) for h in r['landings']['harbours']}
    r['landings']=audit_landings(m,docks)
    routes=[]
    for a in r['action_sites']:
        x,y,z=a['visit'];origin=tuple(a.get('origin',docks.get(a['island'],(62,8,1))))
        route=shortest_route(m,origin,(x,y+1,z),blocked=obstacle_cells(m),land_only=True,diagonal=False)
        if len(route)-1>12:raise ValueError('Well revision exceeds shore travel budget')
        routes.append(dict(island=a['island'],label=a['label'],steps=len(route)-1))
    r['shore_access']=dict(routes=routes,max_steps=max(a['steps'] for a in routes))
    return m,r
