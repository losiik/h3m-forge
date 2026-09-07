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


def seer(required, reward, first, done, *, mission=5):
    return (pack('I', 1) + quest(required, first, done, mission=mission)
            + b'\x08' + artifact(reward) + pack('I', 0) + bytes(2))


def box(message, *, artifacts=(), army=(), resources=(0,)*7, experience=0):
    return (b'\x01' + string(message) + bytes(5)
            + pack('Iibb', experience, 0, 0, 0) + pack('7i', *resources)
            + bytes(5) + bytes([len(artifacts)]) + b''.join(artifact(a) for a in artifacts)
            + b'\x00' + bytes([len(army)]) + b''.join(pack('HH', *u) for u in army)
            + bytes(8) + b'\x00' + pack('iiiB', 0, 0, 31, 0))


def monster(identifier, count, message, trophy):
    # Monster rewards still use a two-byte artifact ID in revision 9.
    return (pack('IHBB', identifier, count, 4, 1) + string(message) + bytes(28)
            + pack('H', trophy) + bytes([1, 1, 0, 0])
            + pack('iBiii', -1, 0, 100, -1, -1) + bytes(5))


def hero(*, army=((1, 60), (3, 45), (6, 28), (0, 12)), artifacts=(7,), spells=(), equipped=None):
    skills = ((0, 3), (2, 3), (5, 3), (23, 2), (22, 2))
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
    return (pack('IBB', 10001, 0, 0) + b'\x01' + string('Одиссей')
            + b'\x01' + pack('I', 0) + b'\x00' + b'\x01' + pack('I', len(skills))
            + b''.join(bytes(s) for s in skills) + b'\x01'
            + b''.join(pack('HH', *u) for u in army)
            + pack('HH', 65535, 0) * (7-len(army)) + b'\x00'
            + b'\x01' + b''.join(artifact(a) for a in slots) + pack('H', len(artifacts)) + b''.join(artifact(a) for a in artifacts)
            + b'\xff\x01' + string('Царь Итаки. После падения Трои он ведёт спутников домой. Хитрость и стойкость помогут там, где бессилен меч.')
            + b'\x00' + b'\x01' + bytes(spell_mask) + b'\x01' + bytes([4, 4, 2, 2])
            + bytes(16) + pack('BBi', 0, 0, 1))


def town(name, owner=255):
    from h3m.hota import town_payload
    raw = town_payload(20001 if owner == 0 else 20002, owner)
    return raw[:5] + b'\x01' + string(name) + raw[6:]
