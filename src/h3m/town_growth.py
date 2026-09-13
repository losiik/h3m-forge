"""Native HotA 1.8 town recruitment and calendar events (no extended scripts)."""
from h3m.authored import pack, string


def expedition_town(name, *, owner, identifier):
    """A fixed expedition base: fort and hall, no recruitment or construction.

    Explicit masks avoid difficulty-dependent default starting dwellings.
    Keeping a town also prevents the native seven-day townless defeat rule.
    """
    if owner not in range(8):
        raise ValueError('Invalid town owner')
    built = {0, 3}
    buildings = sum(1 << b for b in built).to_bytes(6, 'little')
    forbidden = sum(1 << b for b in range(41) if b not in built).to_bytes(6, 'little')
    return (pack('IBB', identifier, owner, 1) + string(name) + bytes([0, 0, 1])
            + buildings + forbidden + bytes(18) + bytes([0]) + pack('I', 48)
            + bytes(48) + pack('I', 0) + bytes([255, 0, 0, 0]))


def growth_town(name, *, owner=1, identifier=20002, first_day=8, repeat_days=7):
    # H3M mask indexes differ from the engine's BuildingID enum.
    # VCMI config/gameConfig.json: hall=0, fort/citadel/castle=3/4/5,
    # dwellings 1/2/4 and upgrades=22/23,25/26,31/32.
    built={0,3,4,5,22,23,25,26,31,32}
    buildings=sum(1<<b for b in built).to_bytes(6,'little')
    forbidden=sum(1<<b for b in range(41) if b not in built).to_bytes(6,'little')
    event=(string('Сбор дружины Антиноя')+string('К женихам прибывают новые стрелки и мечники.')
        +pack('7i',0,0,0,0,0,0,10000)+bytes([1<<owner,0,1])
        +pack('HH',first_day-1,repeat_days)+bytes(16)+pack('IB',31,0)
        +pack('iiihB',0,48,0,0,0)+bytes(6)+pack('7H',0,8,0,5,0,0,0)+bytes(4))
    return (pack('IBB',identifier,owner,1)+string(name)+bytes([0,0,1])
        +buildings+forbidden+bytes(18)+bytes([0])+pack('I',48)+bytes(48)
        +pack('I',1)+event+bytes([255,0,0,0]))


def siege_town(name, *, owner=1, identifier=20002, wave_days=(15,29,43)):
    """Only archers grow naturally; three finite mobilization bonuses.

    This caps additional waves, NOT the native weekly dwelling pool. Hiring
    and transfer to a visiting hero remain native AI decisions.
    """
    if owner not in range(8) or any(type(day) is not int or not 1<=day<=65536 for day in wave_days):
        raise ValueError('Invalid siege town owner or wave day')
    if len(set(wave_days))!=len(wave_days):raise ValueError('Duplicate mobilization day')
    built={0,3,25,26}  # town hall, fort, archer tower and upgrade; no castle growth multiplier
    buildings=sum(1<<b for b in built).to_bytes(6,'little')
    forbidden=sum(1<<b for b in range(41) if b not in built).to_bytes(6,'little')
    events=[]
    for day in wave_days:
        events.append(string('Сбор стрелков Антиноя')+string('Во дворец прибыло подкрепление.')
            +pack('7i',0,0,0,0,0,0,4000)+bytes([1<<owner,0,1])
            +pack('HH',day-1,0)+bytes(16)+pack('IB',31,0)
            +pack('iiihB',0,48,0,0,0)+bytes(6)+pack('7H',0,6,0,0,0,0,0)+bytes(4))
    return (pack('IBB',identifier,owner,1)+string(name)+bytes([0,0,1])
        +buildings+forbidden+bytes(18)+bytes([0])+pack('I',48)+bytes(48)
        +pack('I',len(events))+b''.join(events)+bytes([255,0,0,0]))
