"""Authored adventure objects for native HotA 1.8 / revision 9.

HotA artifact+spell pairs and quest counters differ from the SoD builders.
Layouts follow the editor probes and VCMI's MapFormatH3M reader.
"""
import struct


def pack(fmt, *values):
    return struct.pack('<' + fmt, *values)


def string(value):
    raw = value.encode('cp1251')
    return pack('I', len(raw)) + raw


def artifact(value):
    # The native editor requires zero in the spell word for ordinary items.
    # VCMI ignores that word for non-scrolls, which can hide invalid files.
    return pack('HH', value, 65535 if value == 65535 else 0)


def quest(required, first, done, *, mission=5):
    if mission == 4:
        body = pack('I', required[0])
    elif mission == 5:
        body = bytes([len(required)]) + b''.join(artifact(a) for a in required)
    elif mission == 6:
        body = bytes([len(required)]) + b''.join(pack('HH', *unit) for unit in required)
    elif mission == 7:
        body = pack('7I', *required)
    elif mission == 8:
        body = bytes([required[0]])
    else:
        raise ValueError('unsupported quest mission')
    return (bytes([mission]) + body + pack('I', 0xffffffff) + string(first)
            + string('Испытание ещё не завершено. ' + first) + string(done))


def seer(required, reward, first, done, *, mission=5, reward_kind=8):
    if reward_kind==8:body=artifact(reward)
    elif reward_kind in (6,7):body=bytes(reward)
    elif reward_kind==10:body=pack('HH',*reward)
    else:raise ValueError('Unsupported seer reward kind')
    return (pack('I', 1) + quest(required, first, done, mission=mission)
            + bytes([reward_kind]) + body + pack('I', 0) + bytes(2))


def box(message, *, artifacts=(), army=(), resources=(0,)*7, experience=0):
    return (b'\x01' + string(message) + bytes(5)
            + pack('Iibb', experience, 0, 0, 0) + pack('7i', *resources)
            + bytes(5) + bytes([len(artifacts)]) + b''.join(artifact(a) for a in artifacts)
            + b'\x00' + bytes([len(army)]) + b''.join(pack('HH', *u) for u in army)
            + bytes(8) + b'\x00' + pack('iiiB', 0, 0, 31, 0))


def monster(identifier, count, message, trophy, *, resources=(0,)*7,
            upgraded_stack=-1, stack_count=-1):
    if type(upgraded_stack) is not int or upgraded_stack not in (-1, 0, 1):
        raise ValueError('upgraded_stack must be -1 (random), 0 (never), or 1 (always)')
    if type(stack_count) is not int or stack_count not in (-1, 1, 2, 3, 4, 5, 6, 7):
        raise ValueError('stack_count must be -1 or 1..7')
    if stack_count > count:
        raise ValueError('stack_count cannot exceed creature count')
    # Monster rewards still use a two-byte artifact ID in revision 9.
    has_message=bool(message or any(resources) or trophy!=65535)
    contents=(string(message)+pack('7i',*resources)+pack('H',trophy)) if has_message else b''
    return (pack('IHBB', identifier, count, 4, has_message) + contents + bytes([1, 1, 0, 0])
            + pack('iBiii', -1, 0, 100, upgraded_stack, stack_count) + bytes(5))


def hero(*, name='Герой', biography='', army=((1, 60), (3, 45), (6, 28), (0, 12)), artifacts=(7,), spells=(), equipped=None,
         owner=0, hero_id=0, identifier=10001, patrol=255, experience=0,
         primary=(4,4,2,2), skills=((0,3),(2,3),(5,3),(23,2),(22,2))):
    if owner not in range(8) or not 0<=hero_id<215 or not 0<=patrol<=255:
        raise ValueError('Invalid authored hero owner, type or patrol')
    spell_mask=bytearray(9)
    for spell in spells:
        if type(spell) is not int or not 0<=spell<70:
            raise ValueError('Invalid hero spell')
        spell_mask[spell//8] |= 1 << (spell%8)
    slots=[65535]*19
    if spells:
        slots[17]=0  # SPELLBOOK slot and artifact ID, VCMI EntityIdentifiers.h
    for slot,item in (equipped or {}).items():
        if type(slot) is not int or not 0<=slot<19 or type(item) is not int or not 0<=item<65535:
            raise ValueError('Invalid equipped artifact')
        slots[slot]=item
    return (pack('IBB', identifier, owner, hero_id) + b'\x01' + string(name)
            + b'\x01' + pack('I', experience) + b'\x00' + b'\x01' + pack('I', len(skills))
            + b''.join(bytes(s) for s in skills) + b'\x01'
            + b''.join(pack('HH', *u) for u in army)
            + pack('HH', 65535, 0) * (7-len(army)) + b'\x00'
            + b'\x01' + b''.join(artifact(a) for a in slots) + pack('H', len(artifacts)) + b''.join(artifact(a) for a in artifacts)
            + bytes([patrol,1]) + string(biography)
            + b'\x00' + b'\x01' + bytes(spell_mask) + b'\x01' + bytes(primary)
            + bytes(16) + pack('BBi', 0, 0, 1))


def town(name, owner=255):
    from h3m.hota import town_payload
    raw = town_payload(20001 if owner == 0 else 20002, owner)
    return raw[:5] + b'\x01' + string(name) + raw[6:]
