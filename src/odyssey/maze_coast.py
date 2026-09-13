"""Carve coves and bent waterways into one continuous natural landmass."""
from collections import Counter
from random import Random

from h3m import catalog
from h3m.terrain import Terrain
from h3m.pacing import obstacle_cells
from odyssey.barriers import natural_cap_template


def carve(m,assets,segments,docks,protected,bay_land,seed):
    rng=Random(seed);water=set()
    for (ax,ay),(bx,by) in segments:
        if ax!=bx and ay!=by:raise ValueError('Orthogonal control segments required')
        for x in range(min(ax,bx),max(ax,bx)+1):
            for y in range(min(ay,by),max(ay,by)+1):
                for xx in range(max(0,x-1),min(72,x+2)):
                    for yy in range(max(0,y-1),min(72,y+2)):
                        water.update((xx//2*2+dx,yy//2*2+dy,0) for dx in (0,1) for dy in (0,1))
    fairways={(x,yy,z) for x,y,z in docks.values() for yy in range(y+1,min(72,y+5))}
    for x,y,z in fairways:
        water.update((x//2*2+dx,y//2*2+dy,z) for dx in (0,1) for dy in (0,1))
    land=protected|bay_land;water.difference_update(land)
    # Remove the original circular reef rings and cap decorations. Their real
    # masks will be replaced by mainland scenery; interactive objects stay put.
    def retain(o):
        if o.z or not 114<=o.object_id<=161:return True
        t=m.object_templates[o.template_index]
        cells={(o.x+dx,o.y+dy,o.z) for dx,dy in t.blocked_cells()}
        return bool(cells) and cells<=protected
    m.objects=[o for o in m.objects if retain(o)]
    data=bytearray(m.terrain.data)
    converted={(x,y,0) for y in range(72) for x in range(72)}-land-water
    for c in converted:data[m.terrain.offset_of(*c)]=Terrain.SAND
    for c in water:data[m.terrain.offset_of(*c)]=Terrain.WATER
    for c in bay_land:data[m.terrain.offset_of(*c)]=Terrain.SAND
    # A sand fringe separates different native soils. Inside the mainland,
    # woods and mountains replace the uniform straight palm fences of v5.
    for y in range(2,70,2):
        for x in range(2,70,2):
            surrounding={(xx,yy,0) for xx in range(x-2,x+4) for yy in range(y-2,y+4)}
            if surrounding<=converted:
                for dx in (0,1):
                    for dy in (0,1):data[m.terrain.offset_of(x+dx,y+dy,0)]=Terrain.GRASS
    m.terrain.data=bytes(data);assets.terrain.apply(m.terrain,seed=seed)
    counts=Counter()
    for soil in (Terrain.SAND,Terrain.GRASS):
        remaining={c for c in converted if m.terrain.tile(*c).terrain==soil}
        palette=[t for ts in assets.templates.values() for t in ts if t.allows_terrain(soil)
                 and not t.visitable_cells() and t.blocked_cells() and natural_cap_template(t,soil)]
        # Fit each anchor against several native shapes instead of tiling an
        # entire coast with whichever large sprite happened to sort first.
        for anchor in sorted(remaining,reverse=True):
            candidates=[]
            for t in palette:
                footprint={(anchor[0]+dx,anchor[1]+dy,0) for dx,dy in t.blocked_cells()}
                if footprint<=remaining:candidates.append((t,footprint))
            if not candidates:continue
            largest=max(len(cells) for _,cells in candidates)
            candidates=[pair for pair in candidates if len(pair[1])>=max(1,largest-1)]
            t,footprint=rng.choice(candidates)
            catalog.place(m,catalog.BorrowedObject(t,b'','continuous maze mainland'),*anchor)
            remaining.difference_update(footprint);counts[t.object_id]+=1
        # Some native footprints do not block their sprite anchor. Revisit
        # the remaining anchors with smaller shapes to close those holes.
        for t in sorted(palette,key=lambda t:len(t.blocked_cells())):
            for anchor in sorted(remaining,reverse=True):
                footprint={(anchor[0]+dx,anchor[1]+dy,0) for dx,dy in t.blocked_cells()}
                if footprint<=remaining:
                    catalog.place(m,catalog.BorrowedObject(t,b'','mainland infill'),*anchor)
                    remaining.difference_update(footprint);counts[t.object_id]+=1
        if remaining:raise ValueError('Unblocked mainland after natural coast packing')
    # Keep all landfalls inside their designated fairway. Only a shore next to
    # a carved channel needs a reef; there are no decorative rings around rooms.
    reef=next(t for ts in assets.templates.values() for t in ts if t.object_id in (147,161)
              and t.blocked_cells()==[(0,0)] and not t.visitable_cells() and t.allows_terrain(8))
    shores={c for c in water if c not in fairways and any((c[0]+dx,c[1]+dy,0) in land
            for dx in (-1,0,1) for dy in (-1,0,1))}
    for c in sorted(shores):catalog.place(m,catalog.BorrowedObject(reef,b'','shore approach'),*c)
    assert converted<=obstacle_cells(m)
    return converted,dict(counts),sorted(shores)
