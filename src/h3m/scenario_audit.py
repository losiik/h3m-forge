"""Progression proof over the serialized map; deliberately no combat simulation."""
from collections import Counter, deque

from h3m import mapfile
from h3m.adventure import read_monster, read_reward
from h3m.pacing import obstacle_cells
from h3m.stream import BinaryReader


def read_condition(payload):
    r=BinaryReader(payload);mission=r.u8()
    if mission==4: req=(r.u32(),)
    elif mission==5:
        req=[]
        for _ in range(r.u8()):
            req.append(r.u16())
            if r.u16()!=0:raise ValueError('Noncanonical quest artifact')
        req=tuple(req)
    elif mission==6:req=tuple((r.u16(),r.u16()) for _ in range(r.u8()))
    elif mission==7:req=tuple(r.u32() for _ in range(7))
    elif mission==8:req=(r.u8(),)
    else:raise ValueError('Unsupported scenario condition')
    if r.u32()!=0xffffffff:raise ValueError('Unexpected quest deadline')
    for _ in range(3):r.string()
    r.expect_end()
    return mission,req


def reachable(m,start,blocked):
    queue=deque([start]);seen=set()
    while queue:
        cell=queue.popleft()
        if cell in seen or cell in blocked:continue
        x,y,z=cell
        if not (0<=x<m.header.size and 0<=y<m.header.size) or m.terrain.tile(*cell).terrain==9:continue
        seen.add(cell)
        queue.extend((x+dx,y+dy,z) for dx in (-1,0,1) for dy in (-1,0,1) if dx or dy)
    return seen


def audit_scenario(m,report):
    raw=mapfile.serialize(m); m=mapfile.parse(raw)
    if m.tail or m.stopped_at or mapfile.serialize(m)!=raw:raise ValueError('Scenario binary roundtrip failed')
    spec=report['specification'];by_id={c['id']:c for c in spec['chapters']}
    def visit(o):
        dx,dy=m.object_templates[o.template_index].visitable_cells()[0]
        return o.x+dx,o.y+dy,o.z
    gates={visit(o):(o,read_condition(o.payload)) for o in m.objects if o.object_id==215}
    monsters={visit(o):(o,read_monster(o.payload)) for o in m.objects if o.object_id==54}
    boxes={visit(o):(o,read_reward(o.payload,event=o.object_id==26)) for o in m.objects if o.object_id in (6,26)}
    gate_info={tuple(g['position']):g for g in report['gates']}
    completion_info={tuple(c['position']):c for c in report['completions']}
    if {o.position for o,_ in gates.values()}!=set(gate_info):raise ValueError('Missing or extra quest gate')
    if not set(completion_info)<={o.position for o,_ in boxes.values()}:raise ValueError('Missing completion event')
    for o,q in gates.values():
        g=gate_info[o.position]
        if g['role']=='entry':
            expected=tuple(t['artifact'] for t in report['tokens'] if t['child']==g['chapter'])
            if q!=(5,expected):raise ValueError('Entry condition changed')
        else:
            challenge=by_id[g['chapter']]['challenge'];kind=challenge['kind']
            ordinal=next(i for i,c in enumerate(report['chapters']) if c['id']==g['chapter'])
            expected={'visit':(8,(0,)), 'battle':(4,(30000+ordinal,)),
                      'resources':(7,tuple(challenge['resources'])),
                      'army':(6,tuple(map(tuple,challenge['army']))),
                      'artifacts':(5,tuple(challenge['artifacts']))}[kind]
            if q!=expected:raise ValueError('Completion condition changed')
        if q[0]==4 and q[1][0] not in {v['identifier'] for _,v in monsters.values()}:
            raise ValueError('Quest references missing monster')
    ids=[v['identifier'] for _,v in monsters.values()]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate monster identifier')
    permanent=obstacle_cells(m)
    all_optional={tuple(o['position']) for o in report['opportunities']}
    chapter_land={c['id']:set(map(tuple,c['land'])) for c in report['chapters']}
    traces=[]
    def run(skip_optional):
        items=Counter();army=Counter(dict(spec['army']));funds=[0]*7;killed=set()
        closed=set(gates);alive=set(monsters);collected=set();completed=set();trace=[]
        expected={c['id'] for c in spec['chapters'] if not skip_optional or not c['optional']}
        def adjacent(cell,seen):
            x,y,z=cell
            return any((x+dx,y+dy,z) in seen for dx in (-1,0,1) for dy in (-1,0,1) if dx or dy)
        def eligible(q):
            kind,req=q
            if kind==4:return req[0] in killed
            if kind==5:return all(items[a]>=n for a,n in Counter(req).items())
            if kind==6:return all(army[c]>=n for c,n in req) and sum(army.values())>sum(n for _,n in req)
            if kind==7:return all(a>=b for a,b in zip(funds,req))
            return req==(0,)
        def pay(q):
            kind,req=q
            if kind==5:items.subtract(req)
            if kind==6:
                for c,n in req:army[c]-=n
            if kind==7:
                for i,n in enumerate(req):funds[i]-=n
        for _ in range(len(m.objects)*2):
            seen=reachable(m,tuple(report['start']),permanent|closed|alive)
            # All blocked shores and completion pockets must resist diagonal bypass.
            for cell in closed:
                o,q=gates[cell];g=gate_info[o.position];key=g['chapter']
                if g['role']=='entry' and seen & chapter_land[key]:raise ValueError(f'Early island bypass: {key}')
                if g['role']=='entry':
                    sea_ids={v['identifier'] for v in report['battles'] if v['chapter']==key and v['identifier']>=40000}
                    if any(info['identifier'] in sea_ids and adjacent(pos,seen) for pos,(_,info) in monsters.items()):
                        raise ValueError(f'Sea battle accessible before entry: {key}')
                if g['role']=='completion':
                    target=next(tuple(c['position']) for c in report['completions'] if c['chapter']==key)
                    if target in seen:raise ValueError(f'Completion pocket bypass: {key}')
            changed=False
            for cell in sorted(closed):
                o,q=gates[cell];g=gate_info[o.position]
                if skip_optional and by_id[g['chapter']]['optional']:continue
                if adjacent(cell,seen) and eligible(q):
                    pay(q);closed.remove(cell);trace.append('gate:'+g['chapter']+':'+g['role']);changed=True;break
            if changed:continue
            for cell in sorted(alive):
                if adjacent(cell,seen):
                    o,r=monsters[cell];alive.remove(cell);killed.add(r['identifier'])
                    trace.append('battle:'+str(r['identifier']));changed=True;break
            if changed:continue
            for cell,(o,r) in boxes.items():
                if cell in collected or skip_optional and o.position in all_optional:continue
                completion=completion_info.get(o.position)
                if completion and completion['chapter']==spec['finale'] and not expected-{spec['finale']}<=completed:
                    continue  # choose optional branches before triggering native victory
                accessible=cell in seen if o.object_id==26 else (cell[0],cell[1]+1,cell[2]) in seen
                if not accessible:continue
                if o.object_id==26 and (r['once']!=1 or not r['human'] or r['players']!=1):
                    raise ValueError('Scenario event must be once-only and human-enabled')
                for a,spell in r['artifacts']:items[a]+=1
                for c,n in r['army']:army[c]+=n
                for i,n in enumerate(r['resources']):funds[i]+=n
                if len([c for c,n in army.items() if n>0])>7:raise ValueError('Rewards overflow the seven army slots')
                if sum(items.values())>64:raise ValueError('Story inventory exceeds backpack capacity')
                collected.add(cell);changed=True
                if o.position in completion_info:
                    c=completion_info[o.position];key=c['chapter']
                    if not set(by_id[key]['requires'])<=completed:raise ValueError('Chapter completed before its prerequisites')
                    actual=[a for a,s in r['artifacts']]
                    if any(actual.count(a)!=1 for a in c['artifacts']):raise ValueError('Missing or duplicate completion seal')
                    completed.add(key);trace.append('complete:'+key)
                break
            if not changed:break
        if not expected<=completed or items[36]!=1:
            raise ValueError(f'Scenario deadlock (skip_optional={skip_optional}): unfinished={sorted(expected-completed)}, funds={funds}')
        return trace
    traces.append(run(True));traces.append(run(False))
    return dict(full_parse=True,roundtrip=True,mandatory_without_optional=True,all_branches_completable=True,
        no_early_island_access=True,no_completion_bypass=True,mandatory_trace=traces[0],all_branches_trace=traces[1],
        assumptions=['Every battle is won without losses; combat difficulty is not proved.',
                     'No extra troops, gold income, marketplace trades or optional rewards needed for mandatory completion.',
                     'Permissive eight-direction movement including boarding overestimates access to detect bypasses.',
                     'No flight, water walking, dimension door, external mods or disposal of story seals.'])
