from copy import deepcopy
from pathlib import Path

import pytest

from h3m import mapfile, paths
from h3m.adventure import read_reward
from h3m.world import Assets
from h3m.pacing import obstacle_cells
from odyssey.labyrinth import generate, START_ARMY
from odyssey.playable import validate, parse_quest


@pytest.fixture(scope='module')
def maze():
    try:files=[p for p in paths.iter_maps() if not p.name.startswith(('Odyssey-','Forge-'))]
    except paths.GameNotFoundError:pytest.skip('Native HotA references required')
    return generate(Assets.cached(files,paths.out_dir()/'world-assets.json'))


def test_crown_is_replaced_by_a_real_battle(maze):
    m,r=maze
    assert r['gameplay_revision']==6 and r['crown_dependency_removed']
    quests=[parse_quest(o.payload,hut=o.object_id==83) for o in m.objects if o.object_id in (83,215)]
    assert all(not(q['mission']==5 and 22 in q['required']) for q in quests)
    assert next(q for q in quests if q.get('reward')==21)['required']==(60000,)
    trace=r['progression_trace']
    assert trace.index('gate:lights')<trace.index('battle:60000')<trace.index('quest:21')<trace.index('gate:giants')
    assert trace[-1]=='quest:36'


def test_missing_winds_cannot_silently_complete_the_quest(maze):
    m,r=deepcopy(maze)
    pos=next(tuple(b['position']) for b in r['encounters'] if b['identifier']==60000)
    m.objects=[o for o in m.objects if not(o.object_id==54 and o.position==pos)]
    with pytest.raises(ValueError,match='missing monster'):validate(m,r)


def test_no_full_reveal_and_optional_coves_are_skippable(maze):
    original,r=maze
    assert not any(o.object_id in (27,37) for o in original.objects)
    assert len(r['labyrinth']['optional_coves'])==2
    assert r['landings']['checked']==16 and r['pacing']['max_steps']<=30
    m=deepcopy(original)
    optional={tuple(c['position']) for c in r['choices'] if c['optional']}
    m.objects=[o for o in m.objects if not(o.object_id==6 and o.position in optional)]
    assert validate(m,r)['sequential_playthrough_model']


def test_maze_walls_are_native_and_closed(maze):
    m,r=maze
    cells=set(map(tuple,r['labyrinth']['blocked_mainland']))
    assert cells and cells<=obstacle_cells(m)
    assert r['shore_access']['max_steps']<=12
    assert mapfile.serialize(m)==mapfile.serialize(mapfile.parse(mapfile.serialize(m)))


def test_walkable_mainland_would_bypass_the_story(maze):
    m,r=deepcopy(maze)
    mainland=set(map(tuple,r['labyrinth']['blocked_mainland']))
    def on_mainland(o):
        t=m.object_templates[o.template_index]
        return bool({(o.x+dx,o.y+dy,o.z) for dx,dy in t.blocked_cells()} & mainland)
    m.objects=[o for o in m.objects if not on_mainland(o)]
    with pytest.raises(ValueError,match='physical bypass|sea trial accessible'):validate(m,r)


def test_inaccessible_event_must_not_award_from_adjacent_tile(maze):
    from h3m import catalog
    from h3m.adventure import Reward
    from odyssey import payloads as p
    m,r=deepcopy(maze)
    # Put a required item on a permanently blocked cell next to the starting
    # hero. The old adjacent-event rule incorrectly granted it from there.
    start=tuple(r['start']);solid=obstacle_cells(m)
    cell=next(c for c in solid if c[2]==0 and max(abs(c[0]-start[0]),abs(c[1]-start[1]))==1)
    template=next(t for t in m.object_templates if t.object_id==26)
    catalog.place(m,catalog.BorrowedObject(template,Reward('Unreachable',artifacts=(22,)).event(),'test'),*cell)
    q=next(q for q in r['quests'] if q['reward']==21)
    obj=next(o for o in m.objects if o.object_id==83 and list(o.position)==q['position'])
    obj.payload=p.seer((22,),21,'Test','Test',mission=5)
    with pytest.raises(ValueError,match='Progression deadlock'):validate(m,r)
