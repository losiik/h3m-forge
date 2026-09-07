"""Independent native event suffix fixtures, not just a symmetric round-trip."""
import struct

import pytest

from h3m.adventure import timed_message
from h3m.events import EventsBlock, read_events, write_events
from h3m.format import MapFeatures, MapFormat
from h3m.stream import BinaryReader, BinaryWriter


@pytest.mark.parametrize('level,suffix',[(5,bytes(14)),(7,struct.pack('<I',31)),
                                      (9,struct.pack('<IB',31,0))])
def test_native_calendar_event_suffix(level,suffix):
    event=timed_message('A','B')
    features=MapFeatures(MapFormat.HOTA,hota_level=level)
    writer=BinaryWriter()
    write_events(writer,EventsBlock([event],bytes(124)),features)
    # Count, strings, resources, players/human/computer, day, 16-bit repeat,
    # 16 reserved bytes, then the version-specific native extension.
    common=(struct.pack('<I',1)+struct.pack('<I',1)+b'A'+struct.pack('<I',1)+b'B'
            +bytes(28)+bytes([1,1,0])+struct.pack('<HH',0,0)+bytes(16))
    assert writer.getvalue()==common+suffix+bytes(124)
    parsed=read_events(BinaryReader(common+suffix+bytes(124)),features)
    assert parsed.events[0].affected_difficulties==31
    assert parsed.events[0].message==b'B'


def test_native_script_event_suffix_is_preserved():
    features=MapFeatures(MapFormat.HOTA,hota_level=9)
    event=timed_message('A','B')
    event.uses_event_system=1
    event.script_event_id=12345
    event.synchronize_objects=1
    writer=BinaryWriter()
    write_events(writer,EventsBlock([event],bytes(124)),features)
    assert writer.getvalue()[-134:-124]==struct.pack('<IBIB',31,1,12345,1)
    parsed=read_events(BinaryReader(writer.getvalue()),features).events[0]
    assert (parsed.uses_event_system,parsed.script_event_id,parsed.synchronize_objects)==(1,12345,1)
