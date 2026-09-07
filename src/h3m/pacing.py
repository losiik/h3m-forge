"""Travel diagnostics for authored adventures, separate from combat balance."""
from collections import deque


def obstacle_cells(m):
    cells=set()
    for o in m.objects:
        t=m.object_templates[o.template_index]
        visits=set(t.visitable_cells())
        cells.update((o.x+x,o.y+y,o.z) for x,y in t.blocked_cells() if (x,y) not in visits)
    return cells


def shortest_route(m, start, goal, *, blocked=frozenset(), water_only=False, land_only=False, diagonal=True):
    """Tile distance; diagonals cannot brush a blocked corner.

    This conservative geometry model does not simulate movement points,
    diagonal movement cost, embarkation or turns in the native engine.
    """
    start,goal=tuple(start),tuple(goal)
    queue=deque([start]); previous={start:None}
    while queue:
        cell=queue.popleft()
        if cell==goal:
            route=[]
            while cell is not None:
                route.append(cell); cell=previous[cell]
            return route[::-1]
        x,y,z=cell
        for dx,dy in ((0,1),(1,0),(0,-1),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)):
            if not diagonal and dx and dy: continue
            other=(x+dx,y+dy,z)
            if other in previous or other in blocked or not (0<=other[0]<m.header.size and 0<=other[1]<m.header.size):
                continue
            tile=m.terrain.tile(*other)
            if tile.terrain==9 or (water_only and not tile.is_water) or (land_only and tile.is_water):
                continue
            # Conservatively require both orthogonal shoulder cells unblocked.
            if dx and dy and ((x+dx,y,z) in blocked or (x,y+dy,z) in blocked):
                continue
            previous[other]=cell; queue.append(other)
    raise ValueError(f'No travel route from {start} to {goal}')


def audit_sea_legs(m, legs, *, max_steps=None):
    blocked=obstacle_cells(m)
    rows=[]
    for label,start,end in legs:
        route=shortest_route(m,start,end,blocked=blocked,water_only=True)
        steps=len(route)-1
        rows.append(dict(label=label,steps=steps,start=list(start),end=list(end)))
    longest=max((r['steps'] for r in rows),default=0)
    if max_steps is not None and longest>max_steps:
        raise ValueError(f'Empty sea leg exceeds budget: {longest} > {max_steps}')
    return dict(legs=rows,total_steps=sum(r['steps'] for r in rows),max_steps=longest,
                distance_model='Eight-neighbour water routes; both corner shoulders must be unblocked; '
                'unit tile costs, no native movement/day estimate.')


def audit_landings(m, docks):
    """Check native landing flags and vacant beaches after clearing harbour guards.

    Deliberately separate from the permissive bypass model. Assumes the
    scenario's guards/sea monsters have been removed by completing their tasks.
    """
    permanent=obstacle_cells(m)
    occupied_land=set()
    for o in m.objects:
        if o.object_id in (26,54,215):
            continue
        t=m.object_templates[o.template_index]
        occupied_land.update((o.x+dx,o.y+dy,o.z) for dx,dy in t.blocked_cells())
    rows=[]
    for key,cell in docks.items():
        x,y,z=cell
        sea=(x,y+1,z)
        beach=m.terrain.tile(*cell)
        if beach.terrain in (8,9) or not beach.flags & 0x40:
            raise ValueError(f'Native landing disabled at {key}: {cell}, flags={beach.flags}')
        if cell in occupied_land or sea in permanent:
            raise ValueError(f'Native landing obstructed at {key}: {cell}')
        water=m.terrain.tile(*sea)
        if not water.is_water or water.flags & 0x40:
            raise ValueError(f'Native harbour water blocked at {key}: {sea}')
        rows.append(dict(island=key,beach=list(cell),sea=list(sea),coastal_flag=True))
    return dict(checked=len(rows),harbours=rows,
                assumptions='Harbour quest guards and sea monsters cleared; no combat simulation.')
