"""Revision 9: scarce earned rewards, limited mana, a growing final antagonist."""
from copy import deepcopy
from dataclasses import replace

from h3m import catalog
from h3m.adventure import Reward, read_monster, read_reward, timed_message
from h3m.authored import hero, monster, quest, seer, pack
from h3m.build import sign_payload
from h3m.pacing import obstacle_cells, shortest_route, audit_landings
from h3m.town_growth import siege_town
from h3m.skills import SecondarySkill
from odyssey.small_company import generate as previous, _reward
from odyssey.playable import validate

FINAL_ARMY=((7,28),(3,32),(11,8),(9,10),(1,30))
LATE_COUNTS={70101:2,70102:5,40003:12,30044:12,40004:12,70019:14,40005:60,50002:16}
TROPHIES={70010:101,30042:28,40002:16,70101:38,70102:39,70019:19,50002:34}
TASKS={
 'troy':'Троянский дозор перекрыл дорогу к кораблю. Пробейтесь к берегу.',
 'ismar':'Киконы преследуют отступающих ахейцев. Разбейте их отряд и уходите из бухты.',
 'lotus':'Разведчики пропали среди лотофагов. Следы ведут к лагерю разбойников.',
 'cyclops':'У пещеры лежат захваченные припасы. Полифем не намерен отпускать гостей. Найдите способ сохранить спутников в бою.',
 'aeolus':'Над островом бушует буря. На берегу Эол ждёт тех, кто сумеет добраться до него.',
 'lights':'Ветры разбили корабль о берег. Усмирите элементалей в глубине острова. Уцелевшие моряки укрылись в хижине. Затем путь лежит к лестригонам.',
 'giants':'Лестригоны обстреливают корабли с берега. Пробейте путь из бухты.',
 'circe':'Кирка знает дорогу в царство теней. В роще шевелятся заколдованные спутники.',
 'hades':'Тиресий ждёт за логовом чудовищ. Их чары обращают друзей друг против друга.',
 'sirens':'Песня сирен заглушает команды. Прорвитесь через отряд в проливе, не теряя строй.',
 'scylla':'Два прохода между скалами: быстрые аспиды на востоке, гидры на западе. Выберите, чем рискнуть.',
 'helios':'Священное стадо заслоняет дорогу. За спокойным берегом скрывается последнее испытание Гелиоса.',
 'calypso':'Калипсо удерживает чужеземцев на острове. Страж берега перекрыл путь к следующему проливу.',
 'phaeacia':'Алкиной встретит путешественников на состязаниях. Отдалённый лагерь хранит ещё одну тайну.',
 'ithaca':'Антиной собрал дружину во дворце. Пока вы странствуете, он нанимает стрелков. Сохраните силы для решающего боя.',
}


def generate(assets,seed=20260905):
    m,r=previous(assets,seed)
    r['gameplay_revision']=9
    r['objectives']=dict(TASKS)
    spells=bytearray(m.meta.allowed_spells)
    spells[35//8] &= ~(1 << (35%8))  # Dispel in Antinous' authored book
    m.meta.allowed_spells=bytes(spells)
    docks={h['island']:tuple(h['beach']) for h in r['landings']['harbours']}

    def erase(o):
        m.objects.remove(o)
        r['action_sites'][:]=[a for a in r['action_sites'] if not(a['object_id']==o.object_id and a['position']==list(o.position))]

    def replace_with_cache(o,reward,key,title):
        # A one-tile Pandora fits wholly inside the old object's footprint.
        old=m.object_templates[o.template_index]
        dx,dy=old.visitable_cells()[0];visit=(o.x+dx,o.y+dy,o.z)
        erase(o)
        t=assets.get(6);dx,dy=t.visitable_cells()[0]
        catalog.place(m,catalog.BorrowedObject(t,reward.pandora(),'earned reward'),visit[0]-dx,visit[1]-dy,visit[2])
        obj=m.objects[-1]
        r['action_sites'].append(dict(island=key,label=title,object_id=6,position=list(obj.position),visit=list(visit)))
        return obj

    # Most battles are passage/escape, not treasure chests with an army icon.
    for b in r['encounters']:
        o=next(o for o in m.objects if o.object_id==54 and list(o.position)==b['position'])
        d=read_monster(o.payload)
        count=LATE_COUNTS.get(d['identifier'],d['count'])
        item=TROPHIES.get(d['identifier'],65535)
        o.payload=monster(d['identifier'],count,TASKS[b['island']] if item!=65535 else '',item,
            upgraded_stack=0,stack_count=d['stack_count'])
        b.update(count=count,artifact=item,gold=0)
    for b in r['sea_encounters']:
        row=next(a for a in r['encounters'] if a['identifier']==b['identifier'])
        b.update(row)

    kept=[]
    for c in r['choices']:
        o=next(o for o in m.objects if o.object_id==6 and list(o.position)==c['position'])
        old=_reward(read_reward(o.payload))
        # Duplicate free recruits and the opening resource chest add no decision.
        if not old.guards and c['island'] not in ('lotus','cyclops'):
            erase(o);continue
        guards=old.guards or (((86,3),) if c['island']=='lotus' else ((0,5),))
        reward=replace(old,guards=guards,resources=(0,)*7,mana=min(old.mana,8),
            experience=min(old.experience,800),movement=0)
        if c['island']=='phaeacia' and c['optional']:
            reward=replace(reward,guards=((7,14),(3,12)),mana=0)
        title={
            'cyclops':'Лагерь у пещеры', 'phaeacia':'Испытание милосердия',
            'lotus':'Пленные разведчики', 'calypso':'Тайник Калипсо',
            'sirens':'Затонувший корабль', 'giants':'Грот уцелевших',
            'circe':'Заколдованная роща', 'aeolus':'Сад Эола', 'troy':'Забытый обоз',
        }[c['island']]
        reward=replace(reward,message=title+'. Внутри слышны голоса. Охрана не пропустит вас без боя.')
        o.payload=reward.pandora()
        c.update(title=title,guards=reward.guards,army=reward.army,resources=reward.resources,
            mana=reward.mana,experience=reward.experience,spells=reward.spells,artifacts=reward.artifacts)
        kept.append(c)
    r['choices']=kept

    # Four optional guarded training camps replace twelve automatic stat pickups.
    camps={'lotus':((86,4),(0,0,0,1)), 'giants':((87,5),(0,1,0,0)),
           'circe':((115,5),(0,0,1,0)), 'phaeacia':((7,10),(2,0,0,0))}
    for t in r['training']:
        o=next(o for o in m.objects if o.object_id==t['object_id'] and list(o.position)==t['position'])
        key=t['island']
        if key not in camps:erase(o);continue
        guard,primary=camps[key]
        reward=Reward('Старый воин ждёт достойного противника. Примите испытание.',guards=(guard,),primary=primary)
        obj=replace_with_cache(o,reward,key,'Испытание наставника')
        r['choices'].append(dict(island=key,title='Испытание наставника',position=list(obj.position),optional=True,
            guards=reward.guards,army=(),resources=(0,)*7,artifacts=(),spells=(),experience=0,mana=0,primary=primary,skills=()))
    r['training']=[]
    r['guarded_training']=4
    # No renewable full mana well. Its one-time guarded stash has a modest refill.
    well=next(o for o in m.objects if o.object_id==48 and list(o.position)==r['wind_island']['well'])
    stash=Reward('В обломках у берега что-то уцелело. Волны скрывают охрану.',guards=((115,3),),mana=12)
    obj=replace_with_cache(well,stash,'lights','Обломки у берега')
    r['choices'].append(dict(island='lights',title='Обломки у берега',position=list(obj.position),optional=True,
        guards=stash.guards,army=(),resources=(0,)*7,artifacts=(),spells=(),experience=0,mana=12,primary=(0,)*4,skills=()))
    r['wind_island'].pop('well')
    r['wind_island']['guarded_mana_cache']=list(obj.position)
    r['wind_island']['added_battles']=1

    # Ambushes mostly mean survival. Only the narrative rescue gives an archangel.
    for a in r['ambushes']:
        o=next(o for o in m.objects if o.object_id==26 and list(o.position)==a['position'])
        old=_reward(read_reward(o.payload,event=True))
        last=a['island']=='sirens'
        reward=Reward('Из тумана налетают преследователи. К бою!',
            guards=((97,4),) if last else old.guards,army=((13,1),) if last else ())
        o.payload=reward.event();a.update(guards=reward.guards,army=reward.army,mana=0)
    # Previously free rewards now require a remembered local battle, never money.
    unlock={'aeolus':40000,'circe':30042,'ismar':30040,'giants':30042,'helios':30044}
    for q in r['quests']:
        if q['mission'] in (7,8):q.update(mission=4,required=(unlock[q['island']],))
        q['first']='Завершите испытание этого берега. Здесь помнят тех, кто пришёл на помощь.'
        q['done']='Теперь здесь спокойно. Примите то, что удалось сохранить.'
        o=next(o for o in m.objects if o.object_id==83 and list(o.position)==q['position'])
        o.payload=seer(q['required'],q['reward'],q['first'],q['done'],mission=q['mission'],reward_kind=q['reward_kind'])
    for s in r['scenes']:
        o=next(o for o in m.objects if o.object_id==26 and list(o.position)==s['position'])
        s['message']=TASKS[s['island']]
        o.payload=Reward(s['message']).event()
    # Lightning belongs to the guarded grove at Aeolus, not its arrival tile.
    c=next(c for c in r['choices'] if c['island']=='aeolus')
    o=next(o for o in m.objects if o.object_id==6 and list(o.position)==c['position'])
    d=replace(_reward(read_reward(o.payload)),spells=(17,))
    o.payload=d.pandora();c['spells']=(17,)
    for g in r['harbour_guards']:
        o=next(o for o in m.objects if o.object_id==215 and list(o.position)==g['position'])
        o.payload=quest(g['required'],'Путь пока закрыт.',TASKS[g['island']],mission=g['mission'])
    for o in m.objects:
        if o.object_id==91:
            key=min((i for i in r['islands'] if i['center'][2]==o.z),key=lambda i:abs(o.x-i['center'][0])+abs(o.y-i['center'][1]))['key']
            o.payload=sign_payload(TASKS[key].encode('cp1251'))
    enemy=next(o for o in m.objects if o.object_id==34 and o.payload[4]==1)
    enemy.payload=hero(name='Антиной',biography='Предводитель женихов. Созывает стрелков во дворец.',
        owner=1,hero_id=1,identifier=71000,patrol=1,experience=25000,primary=(14,14,6,5),
        army=FINAL_ARMY,artifacts=(),spells=(27,35,38,41,53,54),
        skills=((22,3),(23,3),(1,3),(SecondarySkill.EARTH_MAGIC,3),(SecondarySkill.AIR_MAGIC,2)))
    town=next(o for o in m.objects if o.object_id==98 and o.payload[4]==1)
    town.payload=siege_town('Дворец женихов')
    r['finale'].update(army=FINAL_ARMY,growth=dict(enabled=True,wave_days=[15,29,43],extra_archers_per_wave=6,
        natural_archer_growth=9,hard_cap=False,mechanism='Town recruitment pool; hiring and transfer depend on native AI.'))
    r['balance'].update(final_army=FINAL_ARMY,calendar_growth=True,
        counts={str(b['identifier']):b['count'] for b in r['encounters']},
        assumptions='Sparse guarded rewards; stronger late enemies and a recruiting final hero. Native battle balance and AI recruiting require playtest.')
    r['recovery']['shore_mana']=0
    r['reward_policy']=dict(monster_gold=0,trophy_battles=len(TROPHIES),guarded_training=4,
        arrival_bonuses=False,guaranteed_battle_wins=False,
        total_cache_mana=sum(read_reward(o.payload)['mana'] for o in m.objects if o.object_id==6))
    r['chapters']=list(r['quests'])
    r['objects']=len(m.objects)
    r['total_battles']=len(r['encounters'])+sum(bool(c['guards']) for c in r['choices'])+len(r['ambushes'])+1
    m.header.description=('Одиссея, редакция 9. Редкие трофеи за испытания, малый отряд и ограниченная мана. '
        'Антиной собрал сильную дружину и нанимает стрелков, пока вы странствуете. Победите его и верните Итаку.').encode('cp1251')
    m.events.events=[timed_message('Возвращение Одиссея','Пробейтесь к кораблю. Берегите спутников и магию. '
        'На берегах остались пленные и охраняемые тайники. Доход ахейского лагеря уходит на содержание флота. '
        'Антиной собирает во дворце войско; впереди трудное возвращение.')]
    upkeep=timed_message('Содержание ахейского флота','')
    upkeep.resources=pack('7i',0,0,0,0,0,0,-1000)
    upkeep.repeat_days=1
    m.events.events.append(upkeep)
    r['reward_policy']['daily_upkeep']=1000
    r.update(validate(m,r))
    optional={tuple(c['position']) for c in r['choices'] if c['optional']}
    mandatory=deepcopy(m)
    mandatory.objects=[o for o in mandatory.objects if o.object_id!=83 and not(o.object_id==6 and o.position in optional)]
    r['mandatory_without_optional']=validate(mandatory,r)['sequential_playthrough_model']
    r['fork']['verified_alternatives']={str(uid):validate(m,r,avoid_battles={uid})['sequential_playthrough_model'] for uid in r['optional_monster_ids']}
    r['landings']=audit_landings(m,docks)
    solid=obstacle_cells(m);routes=[]
    for a in r['action_sites']:
        x,y,z=a['visit'];origin=tuple(a.get('origin',docks.get(a['island'],(62,8,1))))
        path=shortest_route(m,origin,(x,y+1,z),blocked=solid,land_only=True,diagonal=False)
        if len(path)-1>12:raise ValueError('Reward detour exceeds shore travel budget')
        routes.append(dict(island=a['island'],label=a['label'],steps=len(path)-1))
    r['shore_access']=dict(routes=routes,max_steps=max(a['steps'] for a in routes))
    return m,r
