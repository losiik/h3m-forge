"""Semantic builders/readers for native HotA 1.8 (format revision 9).

Events and Pandora share rewards, but their activation fields precede the
HotA movement extension in DIFFERENT places. See VCMI MapFormatH3M::readEvent,
readPandora and readBoxHotaContent; merely comparing byte lengths misses this.
"""
from dataclasses import dataclass
import struct

from h3m.events import TimedEvent
from h3m.stream import BinaryReader


def pack(fmt, *values):
    return struct.pack('<' + fmt, *values)


def text(value):
    raw = value.encode('cp1251')
    if len(raw) > 16384:
        raise ValueError('Message exceeds 16384 bytes')
    return pack('I', len(raw)) + raw


def army_bytes(army, *, fixed=False):
    if len(army) > 7:
        raise ValueError('At most seven creature stacks')
    if any(type(c) is not int or not 0 <= c < 65535 or type(n) is not int
           or not 1 <= n <= 65535 for c,n in army):
        raise ValueError('Invalid creature ID/count')
    result = b''.join(pack('HH', c,n) for c,n in army)
    return result + pack('HH',65535,0)*(7-len(army)) if fixed else result


@dataclass(frozen=True)
class Reward:
    message: str
    guards: tuple = ()
    army: tuple = ()
    resources: tuple = (0,)*7
    artifacts: tuple = ()
    spells: tuple = ()
    experience: int = 0
    mana: int = 0
    morale: int = 0
    luck: int = 0
    movement: int = 0
    primary: tuple = (0, 0, 0, 0)
    skills: tuple = ()

    def common(self):
        if len(self.resources) != 7 or any(type(v) is not int for v in self.resources):
            raise ValueError('Provide seven integer resource amounts')
        if not 0 <= self.experience <= 0xffffffff or not -3 <= self.morale <= 3 or not -3 <= self.luck <= 3:
            raise ValueError('Invalid experience/morale/luck')
        if len(self.artifacts)>255 or any(type(a) is not int or not 0<=a<65535 for a in self.artifacts):
            raise ValueError('Invalid artifact list')
        if len(self.spells)>70 or any(type(s) is not int or not 0<=s<70 for s in self.spells):
            raise ValueError('Invalid spell list')
        army = army_bytes(self.army)
        if len(self.primary)!=4 or any(type(v) is not int or not 0<=v<=127 for v in self.primary):
            raise ValueError('Provide four primary skill gains, 0..127')
        if len(self.skills)>8 or any(type(s) is not int or not 0<=s<28 or type(level) is not int or not 1<=level<=3 for s,level in self.skills):
            raise ValueError('Invalid secondary skill reward')
        guards = army_bytes(self.guards, fixed=True) if self.guards else b''
        return (b'\x01' + text(self.message) + bytes([bool(self.guards)]) + guards + bytes(4)
                + pack('Iibb', self.experience,self.mana,self.morale,self.luck)
                + pack('7i', *self.resources) + bytes(self.primary) + bytes([len(self.skills)])
                + b''.join(bytes(pair) for pair in self.skills) + bytes([len(self.artifacts)])
                + b''.join(pack('HH',a,0) for a in self.artifacts)
                + bytes([len(self.spells)]) + bytes(self.spells) + bytes([len(self.army)]) + army + bytes(8))

    def extension(self):
        return pack('iiiB',0,self.movement,31,0)

    def pandora(self):
        return self.common() + b'\0' + self.extension()

    def event(self, *, players=1, computer=False, human=True, once=True):
        if type(players) is not int or not 1<=players<=255:
            raise ValueError('Invalid players mask')
        return (self.common() + bytes([players,computer,once]) + bytes(4)
                + bytes([human]) + self.extension())


def timed_message(name, message, *, day=1):
    if type(day) is not int or not 1<=day<=65536:
        raise ValueError('day must be 1..65536')
    text(name)
    text(message)
    return TimedEvent(name.encode('cp1251'),message.encode('cp1251'),bytes(28),
                      1,1,0,day-1,0,bytes(17))


def read_reward(payload, *, event=False):
    r=BinaryReader(payload)
    message=''
    guards=[]
    if r.u8():
        message=r.string().decode('cp1251',errors='replace')
        if r.u8():
            guards=[(r.u16(),r.u16()) for _ in range(7)]
            guards=[u for u in guards if u[0]!=65535]
        r.bytes_(4)
    result=dict(message=message,guards=guards,experience=r.u32(),mana=r.i32(),
                morale=r.i8(),luck=r.i8(),resources=[r.i32() for _ in range(7)],
                primary=list(r.bytes_(4)))
    result['skills']=[(r.u8(),r.u8()) for _ in range(r.u8())]
    result['artifacts']=[(r.u16(),r.u16()) for _ in range(r.u8())]
    result['spells']=[r.u8() for _ in range(r.u8())]
    result['army']=[(r.u16(),r.u16()) for _ in range(r.u8())]
    r.bytes_(8)
    if event:
        result.update(players=r.u8(),computer=r.u8(),once=r.u8())
        r.bytes_(4)
        result['human']=r.u8()
    else:
        r.u8()
    result.update(movement_mode=r.i32(),movement=r.i32(),difficulties=r.i32())
    result['uses_scripts']=r.u8()
    if result['uses_scripts']:
        result.update(script_id=r.i32(),synchronized=r.u8())
    r.expect_end()
    return result


def read_monster(payload):
    r=BinaryReader(payload)
    result=dict(identifier=r.u32(),count=r.u16(),character=r.u8(),has_message=r.u8())
    result['message']=''
    if result['has_message']:
        result.update(message=r.string().decode('cp1251',errors='replace'),
                      resources=[r.i32() for _ in range(7)],artifact=r.u16())
    result.update(never_flees=r.u8(),never_grows=r.u8())
    r.bytes_(2)
    result.update(join_appeal=r.i32(),join_for_money=r.u8(),join_percent=r.i32(),
                  upgraded_stack=r.i32(),stack_count=r.i32())
    r.bytes_(5)
    r.expect_end()
    return result


def edit_monster(payload, *, count=None, message=None):
    info=read_monster(payload)
    if count is None and message is None:
        raise ValueError('Provide count and/or message')
    if count is not None:
        if type(count) is not int or not 1<=count<=65535:
            raise ValueError('count must be 1..65535')
        payload=payload[:4]+pack('H',count)+payload[6:]
    if message is not None:
        if info['has_message']:
            old_size=int.from_bytes(payload[8:12],'little')
            payload=payload[:8]+text(message)+payload[12+old_size:]
        else:
            payload=payload[:7]+b'\x01'+text(message)+bytes(28)+pack('H',65535)+payload[8:]
    return payload
