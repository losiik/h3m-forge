"""Import boundary tests: changed/partial sources must not silently invent stats."""
from pathlib import Path
import runpy
import struct
import pytest

IMPORTER=runpy.run_path(str(Path(__file__).resolve().parents[1]/'tools/build_hota_catalog.py'))
numeric=IMPORTER['numeric']
native_creatures=IMPORTER['native_creatures']
documentation=IMPORTER['documentation']


def test_documentation_markup_and_resource_cost():
    html='''<h4 id="example">Test</h4><ul>
    <li>Level 7, upgraded.</li><li>Attack: <b>20</b>.</li><li>Defense: 20.</li>
    <li>Health: 300.</li><li>Speed: 10.</li><li>Damage: 40–<b>50</b>.</li>
    <li>Shots: 0.</li><li>Cost: 3500 gold + 1 gem.</li>
    <li>Population growth (+building): 1 (+2).</li><li>Amount on map: 3–8.</li>
    <li>AI Value: 6694.</li><li>Fight Value: 5355.</li></ul><h4 id="next">Other</h4>'''
    sections=documentation(html)
    assert 'Other' not in sections['example']
    parsed=numeric(sections['example'])
    assert parsed['cost']==dict(wood=0,mercury=0,ore=0,sulfur=0,crystal=0,gems=1,gold=3500)
    assert parsed['damage_max']==50 and parsed['horde_growth']==2
    for bad in (sections['example'].replace('Health:','HP:'),
                sections['example'].replace('1 gem','one gem')):
        with pytest.raises(ValueError):numeric(bad)


def test_duplicate_section_is_rejected():
    with pytest.raises(ValueError,match='Duplicate'):
        documentation('<h4 id="same">One</h4><h4 id="same">Two</h4>')


def records():
    def string(text):
        value=text.encode('cp1251')
        return struct.pack('<I',len(value))+value
    blob=bytearray()
    for i in range(150,200):
        blob+=string(f'monst{i}')+string(f'Monsters\\monster{i}.str')
        blob+=struct.pack('<II',9,0)
        blob+=b''.join(string(s) for s in ('ab','unit.def','Существо','Существа'))
        stats=[0]*29
        stats[0]=9;stats[14]=35;stats[19]=4;stats[21]=5
        blob+=bytes(16)+b'\x01'+struct.pack('<I',116)+struct.pack('<29I',*stats)
    return blob


def test_native_identity_and_stat_offsets_and_corruption():
    blob=records(); rows=native_creatures(blob)
    assert rows[153]['stats']['attack']==5
    assert rows[153]['stats']['hit_points']==4
    assert rows[153]['stats']['cost']['gold']==35
    assert rows[153]['name_ru']=='Существо'
    for broken in (blob[:-1],blob+blob,blob.replace(b'monster153.str',b'monster154.str'),
                   blob.replace(struct.pack('<I',116),struct.pack('<I',120),1)):
        with pytest.raises(ValueError):native_creatures(broken)
