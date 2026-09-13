import struct
import zlib

import pytest

from h3m import hota, mapfile
from h3m.adventure import Reward
from h3m.instances import ObjectInstance
from h3m.objects import ObjectTemplate
from h3m.preview import describe, render_png


def example():
    m=hota.new_map('Preview data',size=72)
    # Footprint extends into a crop while the anchor remains outside it.
    t=ObjectTemplate(b'TEST.def',bytes([255])*5+bytes([0b00111111]),
                     bytes(5)+bytes([0b01000000]),0,256,26,0,0,0,bytes(16))
    m.object_templates=[t]
    m.objects=[ObjectInstance(10,8,0,0,bytes(5),Reward('Hidden ambush',guards=((115,5),),experience=100).event(),26)]
    return m


def test_preview_crop_preserves_visits_and_hidden_rewards():
    m=example();before=mapfile.serialize(m)
    data,blocked,markers=describe(m,x=8,y=7,width=2,height=3,include_grid=True)
    row=data['objects']['items'][0]
    assert row['anchor']==[10,8,0] and row['visits']==[[9,8,0]]
    assert row['symbol']=='E' and row['reward']['guards']==[(115,5)]
    assert data['tile_grid']['rows'][1][1]=='E'
    assert data['tile_grid']['cell_size']==1
    assert mapfile.serialize(m)==before
    assert describe(m,x=11,y=7,width=2,height=3)[0]['objects']['total']==0


def test_png_is_valid_bounded_and_matches_region():
    m=example();data,blocked,markers=describe(m,x=8,y=7,width=3,height=3)
    png=render_png(m,data,blocked,markers)
    assert png[:8]==b'\x89PNG\r\n\x1a\n'
    pos=8;compressed=b''
    while pos<len(png):
        length=struct.unpack('>I',png[pos:pos+4])[0]
        kind=png[pos+4:pos+8];payload=png[pos+8:pos+8+length]
        crc=struct.unpack('>I',png[pos+8+length:pos+12+length])[0]
        assert zlib.crc32(kind+payload)&0xffffffff==crc
        if kind==b'IHDR':w,h=struct.unpack('>II',payload[:8])
        if kind==b'IDAT':compressed+=payload
        pos+=12+length
    assert w==h==130
    assert len(zlib.decompress(compressed))==h*(w*3+1)


@pytest.mark.parametrize('options',[dict(level=1),dict(x=-1),dict(x=71,width=2),dict(include_grid=True),dict(limit=0)])
def test_preview_rejects_invalid_or_unbounded_requests(options):
    m=example()
    with pytest.raises(ValueError):describe(m,**options)


def test_preview_rejects_incomplete_map_and_paginates():
    m=example()
    data,_,_=describe(m,offset=1,limit=1)
    assert data['objects']['total']==1 and data['objects']['items']==[]
    m.tail=b'unparsed'
    with pytest.raises(ValueError,match='fully parsed'):describe(m)
