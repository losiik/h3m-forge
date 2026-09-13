"""Revision 8: a small expedition, finite opposition, recovery before the finale.

Geometry and revision 7 remain reproducible. Numerical strength is authored,
not a claim that the route validator simulates native tactical battles.
"""
from copy import deepcopy
from dataclasses import replace

from h3m.adventure import Reward, read_reward, read_monster, timed_message
from h3m.authored import hero, monster, quest, seer
from h3m.build import sign_payload
from h3m.skills import SecondarySkill
from h3m.town_growth import expedition_town
from odyssey.rewards_journey import generate as previous
from odyssey.playable import validate

START_ARMY = ((1, 8), (3, 6), (6, 2))
FINAL_ARMY = ((7, 14), (3, 18), (11, 3), (1, 12))
COUNTS = {50000: 10, 30040: 12, 50001: 6, 70010: 1,
          40000: 4, 40006: 14, 60000: 4, 40001: 16, 30042: 3,
          70014: 2, 40002: 50, 70101: 1, 70102: 3,
          40003: 8, 30044: 5, 40004: 8, 70019: 7,
          40005: 24, 50002: 8}


def _reward(info):
    return Reward(info['message'], **{k: info[k] for k in (
        'guards', 'army', 'resources', 'spells', 'experience', 'mana', 'morale',
        'luck', 'movement', 'primary', 'skills')},
        artifacts=tuple(a for a, _ in info['artifacts']))


def generate(assets, seed=20260905):
    m, r = previous(assets, seed)
    r['gameplay_revision'] = 8
    m.header.hota.allowed_difficulties_mask = 31
    # Random special months can spawn new guards, undermining a small finite
    # expedition even when placed monsters never grow.
    m.meta.options.hota_special_months = bytes(4)
    # Map spell masks use inverted bits (1 means banned), unlike hero books.
    # Allow the authored combat curriculum; keep adventure shortcuts banned.
    banned_spells = bytearray([255] * 9)
    for spell in (17, 27, 37, 38, 41, 44, 53, 54):
        banned_spells[spell // 8] &= ~(1 << (spell % 8))
    m.meta.allowed_spells = bytes(banned_spells)
    r['start_army'] = START_ARMY
    player = next(o for o in m.objects if o.object_id == 34 and o.payload[4] == 0)
    player.payload = hero(name='Одиссей', biography='Домой возвращается малый отряд. Каждый спутник важен.',
        army=START_ARMY, artifacts=(), equipped={0: 136}, primary=(4, 4, 3, 4),
        spells=(27, 37, 41, 53, 54),
        skills=((0, 3), (2, 3), (5, 3), (23, 2), (22, 2),
                (SecondarySkill.EARTH_MAGIC, 2), (SecondarySkill.WISDOM, 2)))
    for b in r['encounters']:
        o = next(o for o in m.objects if o.object_id == 54 and list(o.position) == b['position'])
        d = read_monster(o.payload)
        b['count'] = COUNTS[b['identifier']]
        # Random upgraded gorgons could instantly kill the sole archangel.
        # Explicit composition keeps authored encounters stable across runs.
        stacks = 3 if d['identifier'] == 40002 else 1
        o.payload = monster(d['identifier'], b['count'], d['message'], d['artifact'],
                            resources=d['resources'], upgraded_stack=0, stack_count=stacks)
    for b in r['sea_encounters']:
        b['count'] = COUNTS[b['identifier']]

    # Small reinforcements replace mass recruitment; all core supplies are free.
    for c in r['choices']:
        o = next(o for o in m.objects if o.object_id == 6 and list(o.position) == c['position'])
        old = _reward(read_reward(o.payload))
        guards = tuple((unit, max(1, round(n / 7))) for unit, n in old.guards)
        army = tuple((unit, max(1, round(n / 4))) for unit, n in old.army)
        reward = replace(old, guards=guards, army=army)
        key = c['island']
        if key == 'cyclops' and not c['optional']:
            reward = replace(reward, army=((3, 2),), spells=(38,), mana=40,
                message='Дар Афины: два арбалетчика, щит и Воскрешение. Магия земли уже изучена: возвращённые в бою спутники останутся живы после победы. Воскрешайте их до последнего удара по врагу.')
        elif key == 'phaeacia' and c['optional']:
            reward = replace(reward, guards=((7, 6), (3, 4)), army=((13, 1),), mana=40,
                message='Испытание милосердия — необязательно. Шесть крестоносцев и четыре арбалетчика стерегут второго посланника Афины. Победите первым архангелом и спутниками; успейте воскресить павших до конца боя. Награда: ещё один архангел.')
        elif key == 'scylla':
            reward = replace(reward, army=((1, 3),))
        elif key == 'aeolus' and c['optional']:
            reward = replace(reward, guards=((26, 2),))
        if key != 'cyclops' and not (key == 'phaeacia' and c['optional']):
            troop_names = {1:'алебардщики',3:'арбалетчики',6:'мечники',7:'крестоносцы'}
            detail = ', '.join(f'{troop_names.get(unit, str(unit))}: {n}' for unit,n in reward.army)
            reward = replace(reward, message=c['title'].split('\n')[0] + '. '
                + ('Необязательное испытание. ' if c['optional'] else '')
                + ('Спутники присоединятся навсегда: ' + detail + '. ' if detail else '')
                + 'Припасы и обучение помогают сохранить малый отряд.')
        o.payload = reward.pandora()
        c.update(title=reward.message.split('.')[0], guards=reward.guards, army=reward.army,
                 resources=reward.resources, artifacts=reward.artifacts, spells=reward.spells,
                 experience=reward.experience, mana=reward.mana, primary=reward.primary, skills=reward.skills)

    # The third ambush cannot be bypassed (negative route test): the first
    # archangel is a mandatory reward, before the fork and the final act.
    for a, guards in zip(r['ambushes'], (((153, 10), (115, 2)), ((115, 4),), ((97, 2),))):
        o = next(o for o in m.objects if o.object_id == 26 and list(o.position) == a['position'])
        old = _reward(read_reward(o.payload, event=True))
        last = a['island'] == 'sirens'
        reward = replace(old, guards=guards, army=((13, 1),) if last else ((3, 2),), mana=35,
            message=('Из бури вырываются две грозовые птицы. За спасение моряков Афина пошлёт архангела. '
                     'Он может один раз за бой воскресить до 100 здоровья живых союзников. '
                     'Сохраните его и примените дар до гибели последнего врага. Впереди развилка и последние берега.'
                     if last else 'Засада в тумане! После победы два спасённых арбалетчика присоединятся к отряду; вы восстановите силы для дальнейшего пути.'))
        o.payload = reward.event()
        a.update(guards=guards, army=reward.army, mana=reward.mana)

    r['objectives']['cyclops'] = 'Заберите дар Афины у пещеры: щит, двух стрелков и Воскрешение. Магия земли уже изучена. Победите Полифема, сохранив спутников, и получите Глаз циклопа.'
    r['objectives']['phaeacia'] = 'Состязания Алкиноя открывают Итаку. В боковом лагере можно заслужить второго архангела: испытайте воскрешение первого. Обмен Глаза циклопа у мастеров необязателен.'
    r['objectives']['ithaca'] = 'Антиной ждёт у дворца с постоянной дружиной. Недели ожидания не усиливают его. Сохраните архангела для воскрешения спутников. Победа над синим героем завершает карту.'
    from odyssey.wind_island import enrich
    enrich(m, r, assets)
    for s in r['scenes']:
        o = next(o for o in m.objects if o.object_id == 26 and list(o.position) == s['position'])
        s['message'] = r['objectives'][s['island']]
        # One-time refresh on the route; no need to sail home for spell points.
        o.payload = Reward(s['message'], mana=40, movement=250,
            spells=(17,) if s['island'] == 'aeolus' else ()).event()
    for g in r['harbour_guards']:
        o = next(o for o in m.objects if o.object_id == 215 and list(o.position) == g['position'])
        o.payload = quest(g['required'], 'Завершите испытание предыдущей бухты.',
                         r['objectives'][g['island']], mission=g['mission'])
    for o in m.objects:
        if o.object_id == 91:
            key = min((i for i in r['islands'] if i['center'][2] == o.z),
                key=lambda i:abs(o.x-i['center'][0])+abs(o.y-i['center'][1]))['key']
            o.payload = sign_payload(r['objectives'][key].encode('cp1251'))
        elif o.object_id == 98:
            owner = o.payload[4]
            o.payload = expedition_town('Дворец женихов' if owner == 1 else 'Ахейский лагерь',
                                       owner=owner, identifier=20002 if owner == 1 else 20001)
    # Optional archer purchase is a small reinforcement too.
    for q in r['quests']:
        if q['reward_kind'] == 10 and q['mission'] == 7:
            q.update(required=(0,0,0,0,0,0,400), reward=(3,2), first='Два арбалетчика за 400 золота. Найм необязателен.')
            o = next(o for o in m.objects if o.object_id == 83 and list(o.position) == q['position'])
            o.payload = seer(q['required'], q['reward'], q['first'], q['done'], mission=q['mission'], reward_kind=10)

    enemy = next(o for o in m.objects if o.object_id == 34 and o.payload[4] == 1)
    enemy.payload = hero(name='Антиной', biography='Предводитель женихов. Его дружина фиксирована: время не увеличивает армию.',
        owner=1, hero_id=1, identifier=71000, patrol=0, experience=15000,
        primary=(9,9,3,3), army=FINAL_ARMY, artifacts=(), spells=(27,41,53),
        skills=((22,2),(23,2),(1,2)))
    r['finale']['growth'] = dict(enabled=False, mechanism='Fixed army, zero patrol, no town dwellings or recruitment events.')
    r['finale']['army'] = FINAL_ARMY
    r['chapters'] = list(r['quests'])
    r['balance'] = dict(starting_army=START_ARMY, final_army=FINAL_ARMY,
        counts={str(k):v for k,v in COUNTS.items()}, difficulty_levels=[80,100,130,160,200],
        economy_required=False, calendar_growth=False,
        assumptions='Fixed army counts and rewards on every difficulty; native combat and cumulative losses require playtesting.')
    r['recovery'] = dict(first_archangel=r['ambushes'][-1]['position'],
        optional_second_archangel=next(c['position'] for c in r['choices'] if c['island']=='phaeacia' and c['optional']),
        resurrection_cache=next(c['position'] for c in r['choices'] if c['island']=='cyclops' and not c['optional']),
        shore_mana=40, finite_reinforcements=True)
    m.header.description = ('Одиссея, редакция 8: малый отряд. Бесплатные спутники на маршруте, Воскрешение у Полифема, '
        'один архангел по сюжету и второй за испытание. Дружина Антиноя не растёт. '
        'Все пять сложностей поддерживают одинаковые сюжетные награды. Нужна новая игра.').encode('cp1251')
    m.events.events = [timed_message('Малый отряд Одиссея',
        'С вами восемь алебардщиков, шесть арбалетчиков и два мечника. Прикрывайте стрелков, используйте Щит и Лечение. '
        'Спутники и мана ждут на маршруте; в лагере нет найма. У пещеры Полифема заберите Воскрешение. '
        'Позже Афина пошлёт архангела. Женихи больше не получают подкреплений со временем.')]
    r.update(validate(m, r))
    optional = {tuple(c['position']) for c in r['choices'] if c['optional']}
    mandatory = deepcopy(m)
    mandatory.objects = [o for o in mandatory.objects if o.object_id != 83 and not(o.object_id == 6 and o.position in optional)]
    r['mandatory_without_optional'] = validate(mandatory, r)['sequential_playthrough_model']
    r['fork']['verified_alternatives'] = {str(uid):validate(m,r,avoid_battles={uid})['sequential_playthrough_model'] for uid in r['optional_monster_ids']}
    return m, r
