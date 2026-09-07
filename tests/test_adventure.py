"""Native reward offsets: byte-preserving parsing alone cannot detect these bugs."""
import struct

import pytest

from h3m.adventure import Reward, edit_monster, read_monster, read_reward, timed_message
from odyssey import payloads as p


def test_event_activation_precedes_hota_extension():
    reward = Reward('Прибытие', guards=((115,24),(153,45)), army=((3,10),),
                    resources=(20,0,10,0,0,0,0), movement=500, mana=10, artifacts=(22,))
    data = reward.event()
    # Independent layout assertion against native readEvent/readBoxHotaContent.
    assert data[-21:-13] == bytes([1,0,1,0,0,0,0,1])
    assert data[-13:] == struct.pack('<iiiB',0,500,31,0)
    parsed = read_reward(data,event=True)
    assert parsed['guards'] == [(115,24),(153,45)]
    assert parsed['army'] == [(3,10)]
    assert parsed['artifacts'] == [(22,0)]
    assert (parsed['players'],parsed['human'],parsed['computer'],parsed['once']) == (1,1,0,1)
    assert (parsed['mana'],parsed['movement']) == (10,500)
    assert read_reward(reward.pandora())['resources'] == [20,0,10,0,0,0,0]


def test_edit_preserves_monster_quest_id_reward_and_hota_flags():
    original = p.monster(98765,31,'Старый текст',45)
    expected = read_monster(original)
    expected.update(count=62,message='Новый текст гораздо длиннее')
    changed = edit_monster(original,count=62,message=expected['message'])
    assert read_monster(changed) == expected
    assert changed[:4] == original[:4]
    assert changed[-26:] == original[-26:]


@pytest.mark.parametrize('count',[0,-1,65536,True,1.2])
def test_invalid_monster_counts(count):
    with pytest.raises(ValueError):
        edit_monster(p.monster(1,10,'A',65535),count=count)


def test_first_day_message_is_human_only_and_non_repeating():
    event = timed_message('Цель','Отбейте дозор')
    assert (event.first_day,event.repeat_days,event.players) == (0,0,1)
    assert (event.human_affected,event.computer_affected) == (1,0)


def test_spellbook_and_initial_spells_preserve_default_hero():
    default = p.hero()
    customized = p.hero(army=((1,28),(3,16)),artifacts=(),spells=(27,41,53,54))
    assert default != customized
    for spell in (-1,70):
        with pytest.raises(ValueError):
            p.hero(spells=(spell,))
