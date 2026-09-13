"""Fixed difficulty profile for newly authored HotA 1.8 adventures.

This fixes sources of composition variance, not tactical difficulty. It does
not scale counts, calculate battle outcomes, or edit arbitrary imported maps.
"""
from h3m.adventure import read_monster, read_reward
from h3m.authored import monster
from h3m.objtypes import MONSTER_LIKE, Obj
from h3m.stream import BinaryReader
from h3m.town_growth import expedition_town

DIFFICULTIES = (80, 100, 130, 160, 200)


def apply_fixed_profile(m):
    """Mutate a fresh authored map, rejecting unsupported/random content first."""
    if not m.header.hota or m.header.hota.level != 9 or m.tail:
        raise ValueError('Fixed profile requires a fully parsed HotA 1.8 authored map')
    replacements = []
    guards = rewards = towns = 0
    for o in m.objects:
        if o.object_id == 54:
            d = read_monster(o.payload)
            if not d['count']:
                raise ValueError('Fixed profile requires explicit creature counts')
            replacements.append((o, monster(d['identifier'], d['count'], d['message'],
                d.get('artifact', 65535), resources=d.get('resources', (0,)*7),
                upgraded_stack=0, stack_count=max(1, d['stack_count']))))
            guards += 1
        elif o.object_id in (6, 26):
            d = read_reward(o.payload, event=o.object_id == 26)
            if d['difficulties'] != 31 or d['uses_scripts']:
                raise ValueError('Fixed rewards must be present on all five difficulties without scripts')
            rewards += 1
        elif o.object_id == 98:
            r = BinaryReader(o.payload)
            identifier, owner = r.u32(), r.u8()
            name = r.string().decode('cp1251') if r.u8() else 'Лагерь'
            if r.u8():
                raise ValueError('Fixed profile cannot discard an authored town garrison')
            replacements.append((o, expedition_town(name, owner=owner, identifier=identifier)))
            towns += 1
        elif o.object_id in MONSTER_LIKE or o.object_id == Obj.RANDOM_TOWN:
            raise ValueError('Fixed profile cannot contain random creatures or towns')
    if any(e.computer_affected or e.affected_difficulties != 31 or e.uses_event_system
           for e in m.events.events):
        raise ValueError('Fixed profile requires unscripted human calendar events on all difficulties')
    for o, payload in replacements:
        o.payload = payload
    m.header.hota.allowed_difficulties_mask = 31
    m.meta.options.hota_special_months = bytes(4)
    return dict(profile='fixed', difficulty_levels=list(DIFFICULTIES),
        neutral_growth=False, random_upgraded_stacks=False, random_special_months=False,
        town_recruitment=False, identical_authored_rewards=True,
        checked_monsters=guards, checked_rewards=rewards, towns_without_recruitment=towns,
        settings_verified=True, native_combat_verified=False,
        limitations=['Authored counts are unchanged; this profile does not balance battles.',
                     'AI tactics, casualties and completion time require native playtesting.'])
