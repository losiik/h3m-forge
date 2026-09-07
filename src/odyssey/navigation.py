"""Physical chapter locks and mandatory encounters in reef-lined harbours.

Quest guards consume the previous chapter sign once, then disappear. The
destination seer no longer asks for that same sign. Revisited islands remain
open. Reachability checks allow all eight directions, even diagonal corner
cutting, to detect shortcuts conservatively.
"""
from collections import deque
from dataclasses import replace

from h3m import catalog
from h3m.terrain import Terrain
from h3m.stream import BinaryReader
from odyssey import payloads as p


SEA_TRIALS = {
    'aeolus': (115, 18, 'Первая буря Посейдона',
        'Полифем воззвал к отцу. Перед Эолией волны встают стеной: водные элементали бьют в борта. Отразите первую ярость Посейдона!'),
    'lights': (153, 36, 'Голоса в пене',
        'В тумане у огней родины нимфы сбивают гребцов с курса. Их зов обещает короткий путь — прямо на рифы. Удержите корабль в проливе!'),
    'giants': (154, 24, 'Прибой у гавани великанов',
        'После отказа Эола гребцы выбились из сил. Океаниды поднимают встречный прибой. За ними — гавань лестригонов: прорвитесь к берегу.'),
    'sirens': (153, 50, 'Обманчивое затишье',
        'Кирка предупредила о песне сирен, но сначала море испытывает гребцов. Нимфы тянут вёсла под воду. Не дайте развернуть корабль к скалам!'),
    'helios': (115, 24, 'Долгий встречный ветер',
        'После Сциллы шторм не даёт высадиться на Тринакрии. Водные элементали обрушиваются на уцелевших. Защитите гребцов и пробейтесь к стоянке.'),
    'calypso': (115, 28, 'На обломке киля',
        'Молния Зевса разбила корабль. Бой с воплощёнными волнами изображает борьбу Одиссея за жизнь среди обломков. Продержитесь до берега Огигии.'),
    'phaeacia': (153, 65, 'Покрывало Ино',
        'Посейдон снова поднял море. Нимфы окружают плот; покрывало Ино указывает просвет в пене. Прорвитесь к берегу, где вас найдёт Навсикая.'),
}

SEA_CREATURE_NAMES = {115:'Водные элементали',153:'Нимфы',154:'Океаниды'}


def add_object(m, template, position, payload=b''):
    return catalog.place(m, catalog.BorrowedObject(template, b'', 'story navigation'), *position, payload=payload)


def land_of(m, island):
    """Island component before any decoration; all islands must be separate."""
    todo = deque([(island.x,island.y,island.z)])
    seen = set()
    while todo:
        cell = todo.popleft()
        if cell in seen:
            continue
        seen.add(cell)
        x,y,z = cell
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            other = (x+dx,y+dy,z)
            if (0 <= other[0] < m.header.size and 0 <= other[1] < m.header.size
                    and other not in seen and m.terrain.tile(*other).terrain not in (Terrain.WATER,Terrain.ROCK)):
                todo.append(other)
    return seen


def harbours(m, islands):
    result = {}
    for island in islands:
        if island.z:
            continue
        land = land_of(m,island)
        bottom = max(y for x,y,z in land)
        x = min((x for x,y,z in land if y == bottom), key=lambda x:(abs(x-island.x),x))
        result[island.key] = (x,bottom,0)
    return result


def build_barriers(m, assets, islands, chapters, docks, placement):
    reef_templates = sorted({t.animation_file:t for variants in assets.templates.values()
        for t in variants if t.object_id in (147,161) and t.allows_terrain(Terrain.WATER)
        and t.blocked_cells() == [(0,0)] and not t.visitable_cells()}.values(), key=lambda t:t.animation_file)
    if not reef_templates:
        raise ValueError('native single-cell reefs unavailable')
    reef_cells = set()
    lanes = set()
    gates = []
    encounters = []
    first_by_island = {}
    for row in chapters:
        first_by_island.setdefault(row[0], row)
    for island in islands:
        if island.z:
            continue
        land = land_of(m,island)
        expanded = []
        for distance in (2,3):
            cells = {(x+dx,y+dy,z) for x,y,z in land
                     for dy in range(-distance,distance+1) for dx in range(-distance,distance+1)
                     if 0 <= x+dx < m.header.size and 0 <= y+dy < m.header.size}
            expanded.append(cells)
        reef_cells.update(c for c in expanded[1]-expanded[0] if m.terrain.tile(*c).is_water)
        x,y,z = docks[island.key]
        if y+4 >= m.header.size:
            raise ValueError(f'no seaward approach to {island.key}')
        # One-cell fairway. Side reefs prevent landing diagonally around a fight.
        lanes.update((x,yy,z) for yy in range(y+1,y+5))
        reef_cells.update((xx,yy,z) for xx in (x-1,x+1) for yy in range(y+1,y+4))
        if island.key == 'troy':
            continue
        previous = first_by_island[island.key][1]
        position = (x,y+3,z)
        text = (f'{island.name}. Рифы смыкаются перед кораблём. '
                'Передайте знак предыдущей главы хранителю пролива: он откроет проход навсегда. '
                'Открытые проливы позволяют вернуться назад. На острове этот знак повторно не потребуется.')
        # Native monsters also occur at sea with land-only palette masks. For
        # the authored water guard explicitly include water in its terrain mask.
        template = replace(assets.get(215), terrain_mask=assets.get(215).terrain_mask | (1 << Terrain.WATER))
        add_object(m,template,position,p.quest((previous,),text,'Пролив открыт. Рифы расступились: путь к берегу свободен.'))
        gates.append(dict(island=island.key,position=list(position),required=[previous],mission=5))
        placement.occupied.add(position)
        if island.key in SEA_TRIALS:
            creature,count,title,message = SEA_TRIALS[island.key]
            visit = (x,y+1,z)
            template = assets.get(54,creature)
            dx,dy = template.visitable_cells()[0]
            position = (x-dx,y+1-dy,z)
            obj = add_object(m,template,position,p.monster(40000+len(encounters),count,title+'\n\n'+message,65535))
            encounters.append(dict(kind='sea_battle',island=island.key,title=title,message=message,
                creature=creature,creature_name=SEA_CREATURE_NAMES[creature],count=count,
                position=[obj.x,obj.y,obj.z],visit=list(visit)))
            placement.occupied.add(visit)
    reef_cells.difference_update(lanes)
    for index,cell in enumerate(sorted(reef_cells)):
        if not m.terrain.tile(*cell).is_water:
            raise ValueError(f'reef would occupy land: {cell}')
        add_object(m,reef_templates[index % len(reef_templates)],cell)
        placement.occupied.add(cell)

    # The subterranean gate arrives north of this complete wall. A guard is
    # the only opening; Circe's first sign is consumed here, before Tiresias.
    underground = next(i for i in islands if i.key == 'hades')
    land = land_of(m,underground)
    wall = {cell for cell in land if cell[1] == 71}
    guard = (124,71,1)
    rock = next(t for ts in assets.templates.values() for t in ts if t.object_id==140
                and t.allows_terrain(Terrain.SUBTERRANEAN) and t.blocked_cells()==[(0,0)]
                and not t.visitable_cells())
    for cell in sorted(wall-{guard}):
        if cell in placement.occupied:
            raise ValueError(f'Hades wall overlaps story object: {cell}')
        add_object(m,rock,cell)
        placement.occupied.add(cell)
    add_object(m,assets.get(215),guard,p.quest((13,),
        'Только Кирка может отправить живого к Тиресию. Передайте её знак хранителю царства теней.',
        'Путь к Тиресию открыт. Возвращайтесь через те же врата.'))
    placement.occupied.add(guard)
    gates.append(dict(island='hades',position=list(guard),required=[13],mission=5))
    return gates,encounters,len(reef_cells)


def reachable(m, start, blocked, teleport_pairs=()):
    """Optimistic mixed travel: allows diagonal cuts and arbitrary boarding.

If this permissive model cannot bypass a lock, restricting boarding and corner
movement in-game cannot introduce a bypass. It is not a movement-cost model.
"""
    seen = set()
    todo = deque([start])
    pairs = dict(teleport_pairs)
    while todo:
        cell = todo.popleft()
        if cell in seen or cell in blocked:
            continue
        x,y,z = cell
        if not (0<=x<m.header.size and 0<=y<m.header.size and 0<=z<m.header.levels):
            continue
        if m.terrain.tile(*cell).terrain == Terrain.ROCK:
            continue
        seen.add(cell)
        todo.extend((x+dx,y+dy,z) for dy in (-1,0,1) for dx in (-1,0,1) if dx or dy)
        if cell in pairs:
            todo.append(pairs[cell])
    return seen


def validate_progression(m, chapters, challenges, gates, encounters, start=(22,117,0)):
    """Simulate locks, battles and quests in serialized-object geometry.

Combat victory and sufficient quest resources/troops are assumptions. Every
next island and sea encounter must stay inaccessible until its chapter key.
"""
    objects = {(o.x,o.y,o.z):o for o in m.objects if o.object_id in (54,83,215)}
    permanent = set()
    for o in m.objects:
        t = m.object_templates[o.template_index]
        if o.object_id in (54,215):
            continue
        visits = set(t.visitable_cells())
        permanent.update((o.x+dx,o.y+dy,o.z) for dx,dy in t.blocked_cells() if (dx,dy) not in visits)
    gates_by_cell = {tuple(g['position']):g for g in gates}
    for cell,g in gates_by_cell.items():
        obj = objects.get(cell)
        if obj is None or obj.object_id != 215:
            raise ValueError(f'missing physical guard: {g["island"]}')
        reader = BinaryReader(obj.payload)
        if reader.u8()!=5:
            raise ValueError('unexpected guard mission')
        required=[]
        for _ in range(reader.u8()):
            required.append(reader.u16())
            if reader.u16()!=0:
                raise ValueError('noncanonical guard artifact')
        if required!=g['required'] or reader.u32()!=0xffffffff:
            raise ValueError('serialized guard condition differs')
        for _ in range(3):
            reader.string()
        if reader.remaining:
            raise ValueError('unexpected guard payload tail')
    battle_records = [c for c in challenges if c['kind']=='battle']+encounters
    battles = {}
    for b in battle_records:
        o = objects[tuple(b['position'])]
        t = m.object_templates[o.template_index]
        dx,dy = t.visitable_cells()[0]
        battles[o.x+dx,o.y+dy,o.z] = b
    closed,alive = set(gates_by_cell),set(battles)
    acquired = {7}
    done_challenges,completed,history = set(),[],[]
    pairs = (((127,68,0),(127,68,1)),((127,68,1),(127,68,0)))

    def approach(record,seen):
        o = objects[tuple(record['position'])]
        t = m.object_templates[o.template_index]
        dx,dy = t.visitable_cells()[0]
        # All seer huts are approached from the south in the actual placement.
        return (o.x+dx,o.y+dy+1,o.z) in seen

    def adjacent(cell,seen):
        x,y,z=cell
        return any((x+dx,y+dy,z) in seen for dy in (-1,0,1) for dx in (-1,0,1) if dx or dy)

    for _ in range(100):
        seen = reachable(m,start,permanent|closed|alive,pairs)
        # Every unopened island remains sealed, including diagonal landfalls.
        for cell in closed:
            g=gates_by_cell[cell]
            first = next(c for c in chapters if c['island']==g['island'])
            if approach(first,seen):
                raise ValueError(f'physical bypass into {g["island"]}; trace={history}')
            for bcell,b in battles.items():
                if b.get('island')==g['island'] and b.get('kind')=='sea_battle' and adjacent(bcell,seen):
                    raise ValueError(f'sea trial accessible before gate: {g["island"]}')
        for cell in alive:
            b=battles[cell]
            if b['kind']=='sea_battle':
                first=next(c for c in chapters if c['island']==b['island'])
                if approach(first,seen):
                    raise ValueError(f'mandatory sea battle can be bypassed: {b["island"]}')
        changed=False
        for cell in sorted(closed):
            g=gates_by_cell[cell]
            if set(g['required']) <= acquired and adjacent(cell,seen):
                acquired.difference_update(g['required'])
                closed.remove(cell)
                history.append('gate:'+g['island'])
                changed=True
                break
        if changed:
            continue
        for cell in sorted(alive):
            if adjacent(cell,seen):
                b=battles[cell]
                if 'reward' in b:
                    acquired.add(b['reward'])
                alive.remove(cell)
                history.append('battle:'+b['island'])
                changed=True
                break
        if changed:
            continue
        for index,c in enumerate(challenges):
            if c['kind']!='battle' and index not in done_challenges and approach(c,seen):
                acquired.add(c['reward'])
                done_challenges.add(index)
                changed=True
        if changed:
            continue
        for index,c in enumerate(chapters):
            if index in completed:
                continue
            eligible = c['mission']==8 or set(c['required']) <= acquired
            if eligible and approach(c,seen):
                if index != len(completed):
                    raise ValueError(f'chapter skip: {c["title"]}, expected {len(completed)+1}')
                if c['mission']==5:
                    acquired.difference_update(c['required'])
                acquired.add(c['reward'])
                completed.append(index)
                history.append('chapter:'+c['title'])
                changed=True
                break
        if not changed:
            break
    if len(completed)!=len(chapters) or 36 not in acquired or alive or closed:
        raise ValueError(f'progression deadlock: chapters={len(completed)}, keys={acquired}, gates={closed}, fights={alive}')
    return dict(no_early_island_access=True,no_early_sea_trials=True,
                sequential_playthrough_model=True,all_harbours_connected_after_unlocking=True,
                progression_trace=history,
                model_assumptions=['victory in each battle','quest resources and six pikemen available',
                                   'no flight, water walk, dimension door or external modifications'])
