import pytest

from h3m import mapfile, paths
from h3m.adventure import read_reward
from h3m.world import Assets
from h3m.stream import BinaryReader
from h3m.heroes import read_hero_artifacts
from odyssey.well_journey import generate, well_access
from odyssey.playable import validate


@pytest.fixture(scope='module')
def journey():
    try:files=[p for p in paths.iter_maps() if not p.name.startswith(('Odyssey-','Forge-'))]
    except paths.GameNotFoundError:pytest.skip('Native HotA references required')
    return generate(Assets.cached(files,paths.out_dir()/'world-assets.json'))


def test_native_well_and_guard_have_verified_ids_and_no_extra_loot(journey):
    m,r=journey
    wells=[o for o in m.objects if o.object_id==49]
    assert len(wells)==1 and not wells[0].payload
    assert m.object_templates[wells[0].template_index].animation_file.lower()==b'avxwelr0.def'
    assert not any(o.object_id==48 for o in m.objects)  # Spring would double mana.
    o=next(o for o in m.objects if o.object_id==26 and list(o.position)==r['well_trial']['guard_position'])
    d=read_reward(o.payload,event=True)
    assert d['guards']==[(143,30),(142,15)]  # Rogue, Nomad; independently verified native IDs.
    assert d['players']==1 and d['human'] and not d['computer'] and d['once'] and d['difficulties']==31
    assert not d['uses_scripts'] and not d['mana'] and not d['experience']
    assert not any(d['resources']) and not any(d['primary'])
    assert not d['army'] and not d['skills'] and not d['artifacts'] and not d['spells']


def test_guard_blocks_every_well_approach_and_wall_regression_is_detected(journey):
    m,r=journey;trial=r['well_trial']
    beach=next(h['beach'] for h in r['landings']['harbours'] if h['island']=='scylla')
    assert well_access(m,beach,trial['position'],trial['guard_position'])['no_bypass']
    # Removing the right-hand rock next to the approach must expose a bypass.
    broken=mapfile.parse(mapfile.serialize(m))
    x,y,z=trial['position'];hole=(x+1,y+1,z)
    rock=next(o for o in broken.objects if o.position==hole and o.object_id>=114)
    broken.objects.remove(rock)
    with pytest.raises(ValueError,match='without defeating'):
        well_access(broken,beach,trial['position'],trial['guard_position'])


def test_fork_remains_optional_and_previous_balance_survives(journey):
    m,r=journey
    raw=mapfile.serialize(m);parsed=mapfile.parse(raw)
    assert not parsed.tail and mapfile.serialize(parsed)==raw
    assert r['gameplay_revision']==12 and r['total_battles']==41 and r['sea_battles']==12
    assert r['well_trial']['optional_verified'] and r['mandatory_without_optional']
    assert all(r['fork']['verified_alternatives'].values()) and r['landings']['checked']==16
    assert r['shore_access']['max_steps']<=12 and r['well_trial']['access']['steps']<=12
    assert validate(m,r,avoid_ambushes={tuple(r['well_trial']['guard_position'])})['sequential_playthrough_model']
    final_ambush=next(o for o in m.objects if o.object_id==26 and o.position==(69,36,0))
    assert read_reward(final_ambush.payload,event=True)['guards']==[(97,5)]
    assert r['balance']['counts']['40002']==200 and r['reward_policy']['total_cache_mana']==58


def test_antinous_has_reduced_stats_and_no_resurrection_in_native_book(journey):
    m=mapfile.parse(mapfile.serialize(journey[0]))
    enemy=next(o for o in m.objects if o.object_id==34 and o.payload[4]==1)
    p=BinaryReader(enemy.payload)
    assert p.u32()==71000 and p.u8()==1 and p.u8()==1
    if p.u8():p.string()
    if p.u8():p.u32()
    if p.u8():p.u8()
    if p.u8():p.bytes_(p.u32()*2)
    assert p.u8()==1
    army=[(p.u16(),p.u16()) for _ in range(7)]
    assert all(c!=13 for c,n in army)  # No Archangel resurrection either.
    p.u8();read_hero_artifacts(p,m.header.features);p.u8()
    if p.u8():p.string()
    p.u8();assert p.u8()==1
    mask=p.bytes_(9)
    spells={i for i in range(70) if mask[i//8] & (1<<(i%8))}
    assert spells=={27,35,41,53,54} and 38 not in spells
    assert p.u8()==1 and tuple(p.bytes_(4))==(12,12,5,4)
    # Resurrection remains earnable by the player; no map-wide ban was added.
    assert any(38 in read_reward(o.payload)['spells'] for o in m.objects if o.object_id==6)
