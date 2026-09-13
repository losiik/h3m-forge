from types import SimpleNamespace

from h3m import hota, mapfile
from h3m.adventure import Reward, timed_message
from h3m.build import sign_payload
from h3m.narrative import inspect_texts
from h3m.objects import ObjectTemplate
from h3m.instances import ObjectInstance
from odyssey.payloads import seer


def test_text_inventory_preserves_dialogue_roles_and_source():
    m = hota.new_map('Тексты')
    payloads = [(59, sign_payload('Исмар на севере'.encode('cp1251'))),
                (83, seer((10,), 11, 'Первый визит', 'Теперь к огням')),
                (26, Reward('Вход в пролив').event())]
    for kind, payload in payloads:
        t = ObjectTemplate(b'TEST.def', bytes([255])*6, bytes(6), 0, 256,
                           kind, 0, 0, 0, bytes(16))
        m.objects.append(ObjectInstance(3, 4, 0, len(m.object_templates), bytes(5), payload, kind))
        m.object_templates.append(t)
    m.events.events = [timed_message('Старт', 'Плывите на север')]
    raw = mapfile.serialize(m)
    result = inspect_texts(mapfile.parse(raw))
    assert not result['errors'] and result['full_parse']
    assert [x['role'] for x in result['items']] == ['message', 'first', 'repeat', 'completed', 'message', 'timed']
    assert result['items'][0]['text'] == 'Исмар на севере'
    assert result['items'][0]['position'] == [3, 4, 0]
    assert result['items'][3]['text'] == 'Теперь к огням'
    assert result['items'][-1]['first_day'] == 1
    assert mapfile.serialize(m) == raw


def test_partial_inventory_is_explicit_and_malformed_payload_not_guessed():
    m = hota.new_map('Неполная карта')
    m.tail = b'opaque'
    m.object_templates = [SimpleNamespace(object_id=91, object_subid=0)]
    m.objects = [ObjectInstance(1, 1, 0, 0, bytes(5), b'\xff'*4, 91)]
    result = inspect_texts(m)
    assert not result['full_parse']
    assert result['items'] == [] and len(result['errors']) == 1
