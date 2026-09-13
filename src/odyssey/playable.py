"""Gameplay revision 3: actions instead of a trophy delivery circuit.

The previous story remains reproducible in odyssey.story. This revision reuses
its landscape/reef layout, then replaces quests, encounters and player guidance.
"""
from collections import Counter
from dataclasses import replace
from math import hypot
from types import SimpleNamespace

from h3m import catalog, mapfile
from h3m.adventure import Reward, read_monster, read_reward, timed_message
from h3m.build import sign_payload
from h3m.stream import BinaryReader
from odyssey import payloads as p
from odyssey.navigation import harbours, reachable
from odyssey.story import ISLANDS, generate as generate_previous


START_ARMY = ((1,28),(3,16),(6,12),(0,8))
TACTICAL_SPELLS=(27,41,53,54)  # Shield, Bless, Haste, Slow; no adventure shortcuts

# Native defeat-monster quests remember the encounter's ID, not an artifact.
KILL_GATES = dict(ismar=50000, lotus=30040, cyclops=50001, circe=30042,
                  scylla=40002, calypso=30044, ithaca=50002)

CREATURE_NAMES={0:'копейщики',1:'алебардщики',2:'лучники',3:'арбалетчики',6:'мечники',
                7:'крестоносцы',86:'наездники на волках',87:'налётчики',94:'циклопы',
                102:'горгоны',115:'водные элементали',153:'нимфы',154:'океаниды'}

OBJECTIVES = {
    'troy': 'Отбейте троянский дозор к востоку от лагеря. Затем спуститесь к кораблю у южного пляжа и плывите на север, в Исмар. Дозор нужно победить: его поражение откроет пролив Исмара.',
    'ismar': 'Прикройте отступление: победите киконов на восточной стороне острова. После боя сразу плывите на север к лотофагам. Возвращаться с трофеем в хижину не нужно.',
    'lotus': 'Трое разведчиков потерялись в роще. Разбейте разбойников на волках в западной части острова и заберите спасённых у места боя. Лотофаги мирны: вы сражаетесь с разбойниками, а не с жителями. Затем курс на северо-восток, к Полифему.',
    'cyclops': 'Полифема убивать нельзя. В западной хижине приготовьте побег: 30 дерева на кол и 1000 золота на вино. Древесина есть в охраняемом ящике на востоке. Получив план «Никто», сразу плывите на восток к Эолу.',
    'aeolus': 'Переживите бурю у входа. При первом прибытии посетите западную хижину Эола: он даст мех ветров. Затем плывите на юго-восток к огням Итаки. После раскрытия меха вернитесь в восточную хижину Эола.',
    'lights': 'Огни Итаки уже видны. Вход в эту стоянку запускает сцену раскрытого меха. После неё не ищите ещё одну хижину: возвращайтесь к Эолу на север, в восточную хижину. Сам дворец Итаки пока недоступен.',
    'giants': 'Пробейте выход из засады: победите циклопов на востоке острова. Они изображают лестригонов. После победы плывите прямо на юг к Кирке; сдавать трофей не нужно.',
    'circe': 'Спасите заколдованных разведчиков. Для первого разговора с Киркой нужны 7 самоцветов: они лежат в охраняемой роще на востоке. Затем пройдите через северные врата к Тиресию. После пророчества вернитесь в восточную хижину Кирки за советом о сиренах.',
    'hades': 'Здесь не нужно сражаться с умершими. Найдите Тиресия в западной хижине и выслушайте пророчество. Вернитесь через те же врата в восточную хижину Кирки.',
    'sirens': 'Прорвитесь через нимф в проливе. Во время песни не развязывайте Одиссея: это сюжетная сцена, а не бой с самими сиренами. После морского боя можно сразу идти на юго-запад к Сцилле. На берегу есть необязательное испытание.',
    'scylla': 'Отдайте 6 копейщиков в западной хижине: так корабль пройдёт мимо Сциллы. Запасные шестеро ждут в ящике на юго-западе. Получив право прохода, плывите на запад к стадам Гелиоса.',
    'helios': 'Спутники нарушают запрет Тиресия. Бой со стадом на востоке разыгрывает их роковое решение. После него сразу плывите на север к Калипсо. Сдавать трофей не нужно.',
    'calypso': 'Постройте плот: принесите в западную хижину 20 дерева и 10 руды. Материалы можно сохранить заранее или отбить в восточной бухте. Затем плывите на восток к феакам.',
    'phaeacia': 'Пройдите испытание феаков: победите бойцов на западной стороне острова. Это игровое переложение состязаний при дворе Алкиноя. После победы путь на Итаку откроется без доставки подарка в хижину.',
    'ithaca': 'Победите женихов у восточной стороны дворца. Затем идите к Пенелопе в западную хижину: она узнает вас по тайне ложа. Никакого трофея приносить не нужно.',
}

# Six explicitly optional risks, in addition to supplies required by the story.
OPTIONAL = (
    ('troy',(-7,3), 'Забытый ахейский обоз', ((0,24),), ((1,10),), 700),
    ('ismar',(-7,-3), 'Отставшие лучники', ((1,35),(2,10)), ((3,8),), 900),
    ('lotus',(5,-4), 'Лесная тропа', ((86,20),(87,5)), ((6,6),), 1200),
    ('sirens',(5,-4), 'Груз на рифах', ((153,65),(115,14)), ((3,12),), 2500),
    ('calypso',(-6,-3), 'Дары в гроте', ((115,38),), ((6,15),), 3000),
    ('phaeacia',(5,-4), 'Большие состязания', ((7,45),(3,24)), ((7,12),), 4000),
)


def generate(assets, seed=20260905):
    m,old = generate_previous(assets,seed)
    m.header.name='Одиссея: путь морехода'.encode('cp1251')
    m.header.description=('Сюжетная Одиссея, переработка 3. Бои открывают новые берега без доставки трофеев. '
        'Спасение разведчиков, подготовка побега, шесть необязательных испытаний. '
        'Подсказка появляется в первый день и у каждого пролива. Рекомендуется 100%. '
        'Победа после освобождения Итаки и разговора с Пенелопой. Длительность и баланс требуют игрового прогона.').encode('cp1251')
    islands={i.key:i for i in ISLANDS}
    docks=harbours(m,ISLANDS)
    original_huts={tuple(o.position):o for o in m.objects if o.object_id==83}
    m.objects=[o for o in m.objects if o.object_id not in (83,91,6)]
    hero=next(o for o in m.objects if o.object_id==34)
    hero.payload=p.hero(army=START_ARMY,artifacts=(),spells=TACTICAL_SPELLS)
    quests,scenes,choices,battles=[],[],[],[]

    def add(kind, visit, payload=b'', sub=0, *, nearby=False):
        template=assets.get(kind,sub)
        if kind==26:
            template=replace(template,terrain_mask=template.terrain_mask | (1<<8))
        dx,dy=template.visitable_cells()[0]
        candidates=[visit]
        if nearby:
            x,y,z=visit
            candidates=[(x+xx,y+yy,z) for yy in range(-5,6) for xx in range(-5,6)]
            candidates.sort(key=lambda c:(abs(c[0]-x)+abs(c[1]-y),c[1],c[0]))
        for cell in candidates:
            anchor=(cell[0]-dx,cell[1]-dy,cell[2])
            footprint={(anchor[0]+xx,anchor[1]+yy,anchor[2]) for xx,yy in
                       set(template.blocked_cells())|set(template.visitable_cells())}
            if any(not (0<=x<144 and 0<=y<144) or m.terrain.tile(x,y,z).terrain==9
                   or (kind not in (26,59) and m.terrain.tile(x,y,z).is_water) for x,y,z in footprint):
                continue
            overlap=[]
            for o in m.objects:
                t=m.object_templates[o.template_index]
                cells={(o.x+xx,o.y+yy,o.z) for xx,yy in set(t.blocked_cells())|set(t.visitable_cells())}
                if cells & footprint:
                    overlap.append(o)
            if any(not 114<=o.object_id<=140 for o in overlap):
                continue
            for o in overlap:
                m.objects.remove(o)
            catalog.place(m,catalog.BorrowedObject(template,payload,'authored'),*anchor)
            return m.objects[-1]
        raise ValueError(f'No free placement for {kind} near {visit}')

    def box(key, offset, title, *, guards=(), army=(), resources=(0,)*7, xp=0, optional=False):
        i=islands[key]
        details='; '.join(f'{CREATURE_NAMES[c]} — {n}' for c,n in guards)
        troops='; '.join(f'{CREATURE_NAMES[c]} — {n}' for c,n in army)
        materials='; '.join(f'{label} — {n}' for label,n in zip(
            ('дерево','ртуть','руда','сера','кристаллы','самоцветы','золото'),resources) if n)
        message=(f'{title}\n\n'+('НЕОБЯЗАТЕЛЬНО. Можно отказаться и продолжить сюжет.\n' if optional else '')
                 +(f'Охрана: {details}.\n' if guards else '')
                 +f'Награда: {xp} опыта'+(f'; {troops}' if army else '')
                 +(f'; {materials}' if materials else '')+'.')
        o=add(6,(i.x+offset[0],i.y+offset[1],i.z),Reward(message,guards=guards,army=army,
              resources=resources,experience=xp).pandora(),nearby=True)
        record=dict(island=key,title=title,position=list(o.position),guards=guards,army=army,
                    resources=resources,experience=xp,optional=optional)
        choices.append(record)
        return o

    # Adjust existing fights; preserve unique IDs so native kill quests bind correctly.
    counts={30040:65,30042:12,30044:26,30045:115,
            40000:24,40001:44,40002:85,40003:42,40004:46,40005:105,40006:52}
    for o in m.objects:
        if o.object_id==54:
            info=read_monster(o.payload)
            uid=info['identifier']
            o.payload=p.monster(uid,counts[uid],info['message'],65535)
            key=next((r['island'] for r in [*old['challenges'],*old['sea_encounters']]
                      if tuple(r.get('position',r.get('visit',())))==o.position),None)
            battles.append(dict(island=key,identifier=uid,position=list(o.position),
                                creature=m.object_templates[o.template_index].object_subid,count=counts[uid]))
    for key,center,creature,count,uid,message in (
        ('troy',(28,117,0),0,28,50000,'Троянский дозор отрезает отход. Защитите стрелков пехотой. После победы идите к южному пляжу: путь в Исмар будет открыт.'),
        ('lotus',(16,36,0),87,24,50001,'Разбойники на волках окружили троих разведчиков в лотосовой роще. Спасите людей. После боя припасы и пополнение ждут рядом; затем идите к Полифему.'),
        ('phaeacia',(86,84,0),7,70,50002,'Алкиной предлагает показать доблесть на играх. Победа принесёт помощь феаков и откроет проход к Итаке. Потери в тактическом бою настоящие: подготовьте войско!')):
        o=add(54,center,p.monster(uid,count,message,65535),creature,nearby=True)
        battles.append(dict(island=key,identifier=uid,position=list(o.position),creature=creature,count=count))

    # Only meaningful conversations/payments remain; no trophy-return quests.
    specs={
        10:(7,(30,0,0,0,0,0,1000),'План «Никто» готов. Вино усыпит Полифема, кол лишит его зрения. Люди выбрались под баранами. Плывите к Эолу на восток; больше ничего в пещере сдавать не надо.'),
        11:(8,(0,),'Эол запер ветры в мех. Плывите на юго-восток к огням Итаки. Мех — сюжетный предмет: он откроет эту стоянку.'),
        21:(5,(22,),'Эол отказывает вам. Запасного меха не будет. Теперь держите курс на юго-восток, к лестригонам.'),
        13:(7,(0,0,0,0,0,7,0),'Молю разрушает чары Кирки. Разведчики снова люди. Идите через северные врата к Тиресию; после пророчества вернитесь в восточную хижину.'),
        14:(8,(0,),'Тиресий предупреждает: не трогайте стад Гелиоса. Вы услышали пророчество и встретили тень матери. Возвращайтесь к Кирке, в восточную хижину.'),
        15:(5,(14,),'Кирка даёт воск и путы. Теперь курс на юг к сиренам. У Сциллы придётся пожертвовать шестью копейщиками.'),
        17:(6,((0,6),),'Шесть спутников погибли, остальные вырвались из пролива. Плывите на запад к стадам Гелиоса.'),
        19:(7,(20,0,10,0,0,0,0),'Плот готов. Одиссей отвергает бессмертие ради возвращения домой. Плывите на восток, к феакам.'),
        36:(4,(30045,),'Пенелопа испытывает вас тайной брачного ложа, выросшего из живой оливы. Она узнаёт мужа. После двадцати лет Одиссей дома.'),
    }
    for c in old['chapters']:
        if c['reward'] not in specs:
            continue
        mission,required,done=specs[c['reward']]
        o=original_huts[tuple(c['position'])]
        first=OBJECTIVES[c['island']]
        if c['reward']==21:
            first='Вернуться к Эолу после раскрытия меха у огней Итаки. Это восточная хижина; первый подарок вы получаете в западной.'
        elif c['reward']==15:
            first='Выслушайте Тиресия в подземелье и вернитесь сюда за советом о сиренах и Сцилле.'
        o.payload=p.seer(required,c['reward'],first,done,mission=mission)
        m.objects.append(o)
        quests.append(dict(island=c['island'],title=c['title'],mission=mission,required=required,
                           reward=c['reward'],position=list(o.position),first=first,done=done))

    locks=[]
    for g in old['harbour_guards']:
        o=next(o for o in m.objects if o.object_id==215 and list(o.position)==g['position'])
        key=g['island']
        mission=4 if key in KILL_GATES else 5
        required=(KILL_GATES[key],) if mission==4 else tuple(g['required'])
        before=('Этот пролив откроется после выполнения предыдущей боевой задачи. '
                'Трофей приносить не нужно.' if mission==4 else
                'Для прохода нужен сюжетный предмет из предыдущего эпизода. '
                'Он будет передан хранителю; больше его никуда сдавать не надо.')
        o.payload=p.quest(required,islands[key].name+'. '+before,
                          'Пролив открыт.\n\n'+OBJECTIVES[key],mission=mission)
        locks.append(dict(island=key,mission=mission,required=required,position=list(o.position)))

    box('troy',(5,5),'Припасы для выхода в море',resources=(5,0,5,0,0,0,1500))
    box('lotus',(-3,3),'Спасённые разведчики',army=((1,12),(3,8)),xp=500)
    box('cyclops',(5,5),'Древесина для кола и вино Марона',guards=((86,28),(87,8)),
        resources=(30,0,0,0,0,0,1500),xp=1200)
    box('circe',(5,5),'Роща молю: помощь Гермеса',guards=((86,35),(87,16)),
        resources=(0,0,0,0,0,7,0),army=((6,10),),xp=1500)
    box('scylla',(-4,8),'Шестеро гребцов',army=((0,6),))
    box('calypso',(5,5),'Материалы для плота',guards=((115,24),(153,45)),
        resources=(20,0,10,0,0,0,0),xp=2000)
    for key in ('aeolus','circe','calypso','phaeacia'):
        box(key,(5,8),'Союзники пополняют отряд',army=((3,10),(6,10)),xp=500)
    for key,offset,title,guards,army,xp in OPTIONAL:
        box(key,offset,title,guards=guards,army=army,xp=xp,optional=True)

    # Entry messages are on the one-cell fairway, not in an easily missed sign.
    for key,dock in docks.items():
        if key=='troy':
            continue
        cell=(dock[0],dock[1] if key=='lights' else dock[1]+2,0)
        message=islands[key].name+'\n\n'+OBJECTIVES[key]
        arts=(22,) if key=='lights' else ()
        if key=='lights':
            message+='\n\nСпутники раскрыли мех! Ветры отбросили корабль. Теперь возвращайтесь к Эолу.'
        o=add(26,cell,Reward(message,artifacts=arts,movement=500,mana=10).event())
        scenes.append(dict(island=key,position=list(o.position),message=message,artifacts=arts))

    start=('ОДИССЕЯ: ПУТЬ МОРЕХОДА\n\nСейчас: '+OBJECTIVES['troy']+
        '\n\nБои с отмеченными отрядами открывают следующие проливы сами. '
        'В бою у Одиссея есть Щит, Благословение, Ускорение и Замедление; мана ограничена. '
        'В ящиках заранее описаны охрана и награда; помеченные «НЕОБЯЗАТЕЛЬНО» можно пропустить. '
        'На новом берегу подсказка появится автоматически. Победа: освободить Итаку и поговорить с Пенелопой.')
    m.events.events=[timed_message('Начало пути',start)]
    for i in ISLANDS:
        add(91,(i.x-3,i.y+5,i.z),sign_payload((i.name+'\n\n'+OBJECTIVES[i.key]).encode('cp1251')),nearby=True)

    report=dict(gameplay_revision=3,name=m.header.name_text,seed=seed,size=144,levels=2,
        objects=len(m.objects),quests=quests,chapters=quests,harbour_guards=locks,
        scenes=scenes,encounters=battles,choices=choices,optional_battles=len(OPTIONAL),
        field_battles=len(battles),guarded_supply_battles=3,total_battles=len(battles)+len(OPTIONAL)+3,
        sea_battles=7,sea_encounters=[b for b in battles if 40000<=b['identifier']<50000],
        kill_objective_gates=len(KILL_GATES),trophy_delivery_quests=0,
        conversation_quests=len(quests),reefs=old['reefs'],
        decorations=sum(114<=o.object_id<=140 for o in m.objects),
        islands=old['islands'],objectives=OBJECTIVES,start_army=START_ARMY,
        tactical_spells=TACTICAL_SPELLS,
        previous_user_playtime_minutes=20,estimated_hours=None,
        native_editor_checked=False,full_playtest=False,
        adaptations=['Seven chapter items replaced by native defeat-monster conditions.',
                     'Remaining story items are technical quest flags, with native artifact names.',
                     'Years and shipwrecks are narrated; army is not cleared.',
                     'Optional encounters and Phaeacian combat games are gameplay adaptations.'])
    report.update(validate(m,report))
    return m,report


def parse_quest(payload, *, hut=False):
    r=BinaryReader(payload)
    if hut and r.u32()!=1:
        raise ValueError('Expected one quest')
    mission=r.u8()
    if mission==4:
        required=(r.u32(),)
    elif mission==5:
        required=[]
        for _ in range(r.u8()):
            required.append(r.u16())
            if r.u16()!=0:
                raise ValueError('Invalid artifact spell word')
        required=tuple(required)
    elif mission==6:
        required=tuple((r.u16(),r.u16()) for _ in range(r.u8()))
    elif mission==7:
        required=tuple(r.u32() for _ in range(7))
    elif mission==8:
        required=(r.u8(),)
    else:
        raise ValueError('Unexpected quest condition')
    if r.u32()!=0xffffffff:
        raise ValueError('Unexpected deadline')
    messages=[r.string().decode('cp1251') for _ in range(3)]
    reward=None
    reward_kind=None
    if hut:
        reward_kind=r.u8()
        if reward_kind==8:
            reward=r.u16()
            if r.u16()!=0:raise ValueError('Invalid artifact spell word')
        elif reward_kind in (6,7):reward=(r.u8(),r.u8())
        elif reward_kind==10:reward=(r.u16(),r.u16())
        else:raise ValueError('Unexpected quest reward')
        if r.u32()!=0 or r.bytes_(2)!=bytes(2):
            raise ValueError('Unexpected quest extension')
    r.expect_end()
    return dict(mission=mission,required=required,reward=reward,reward_kind=reward_kind,messages=messages)


def validate(m, report, *, avoid_battles=frozenset(), avoid_ambushes=frozenset()):
    """Check native conditions and a permissive playthrough, including resource supply.

    Assumes winning every battle without troop losses. This is a progression
    audit, not a difficulty assessment or a native engine simulation.
    """
    raw=mapfile.serialize(m)
    parsed=mapfile.parse(raw)
    if parsed.stopped_at or parsed.tail or mapfile.serialize(parsed)!=raw:
        raise ValueError(f'Native serialization failed: {parsed.stopped_at}, tail={len(parsed.tail)}')
    objects=parsed.objects
    def visit(o):
        dx,dy=parsed.object_templates[o.template_index].visitable_cells()[0]
        return o.x+dx,o.y+dy,o.z
    gates={visit(o):(o,parse_quest(o.payload)) for o in objects if o.object_id==215}
    huts={visit(o):(o,parse_quest(o.payload,hut=True)) for o in objects if o.object_id==83}
    monsters={visit(o):(o,read_monster(o.payload)) for o in objects if o.object_id==54}
    finale=report.get('finale')
    if finale:
        from h3m.conditions import VictoryType
        enemies=[o for o in objects if o.object_id==34 and o.payload[4]==1]
        if len(enemies)!=1:raise ValueError('Finale needs exactly one blue hero')
        enemy=enemies[0]
        town=next((o for o in objects if o.object_id==98 and o.position==tuple(finale['town'])),None)
        if town is None or visit(enemy) in {
            (town.x+dx,town.y+dy,town.z) for dx,dy in parsed.object_templates[town.template_index].blocked_cells()
        }:
            raise ValueError('Finale hero must stand outside the town footprint')
        if m.victory.kind!=VictoryType.BEAT_HERO or m.victory.allow_normal_victory or m.victory.applies_to_ai or m.victory.payload!=bytes(visit(enemy)):
            raise ValueError('Victory does not target the blue hero visit cell')
        monsters[visit(enemy)]=(enemy,dict(identifier=int.from_bytes(enemy.payload[:4],'little'),artifact=65535,resources=[0]*7))
    rewards={visit(o):(o,read_reward(o.payload,event=o.object_id==26))
             for o in objects if o.object_id in (6,26)}
    guarded_events={cell for cell,(o,r) in rewards.items() if o.object_id==26 and r['guards']}
    expected_gates={tuple(g['position']):g for g in report['harbour_guards']}
    if len(gates)!=len(expected_gates):
        raise ValueError('Missing or duplicate guard')
    for cell,(o,q) in gates.items():
        expected=expected_gates.get(o.position)
        if expected is None or q['mission']!=expected['mission'] or q['required']!=tuple(expected['required']):
            raise ValueError('Serialized gate condition differs')
    ids=[q['identifier'] for o,q in monsters.values()]
    if len(ids)!=len(set(ids)):
        raise ValueError('Duplicate monster quest IDs')
    for o,q in [*gates.values(),*huts.values()]:
        if q['mission']==4 and q['required'][0] not in ids:
            raise ValueError('Defeat quest targets a missing monster')
    permanent=set()
    for o in objects:
        if o.object_id in (54,215):
            continue
        t=parsed.object_templates[o.template_index]
        permanent.update((o.x+dx,o.y+dy,o.z) for dx,dy in t.blocked_cells()
                         if (dx,dy) not in t.visitable_cells())
    acquired=Counter()
    # Read the actual authored hero, rather than assuming the old revision's army.
    hero=next(o for o in objects if o.object_id==34 and o.payload[4]==0)
    hero_reader=BinaryReader(hero.payload)
    hero_reader.bytes_(6)
    if hero_reader.u8():hero_reader.string()
    if hero_reader.u8():hero_reader.u32()
    if hero_reader.u8():hero_reader.u8()
    if hero_reader.u8():hero_reader.bytes_(hero_reader.u32()*2)
    if hero_reader.u8()!=1:raise ValueError('Story hero requires an explicit starting army')
    starting=[(hero_reader.u16(),hero_reader.u16()) for _ in range(7)]
    troops=Counter({c:n for c,n in starting if c!=65535})
    resources=[0]*7  # prove supplies suffice even without the difficulty's initial stock
    killed=set()
    closed,alive=set(gates),set(monsters)
    collected,spoken=set(),set()
    optional_huts={tuple(c) for c in report.get('optional_quest_positions',())}
    history=[]
    pairs=tuple((tuple(a),tuple(b)) for a,b in report.get('teleport_pairs',
        (((127,68,0),(127,68,1)),((127,68,1),(127,68,0)))))
    start=tuple(report.get('start',(22,117,0)))
    def adjacent(cell,seen):
        x,y,z=cell
        return any((x+dx,y+dy,z) in seen for dx in (-1,0,1) for dy in (-1,0,1) if dx or dy)
    def eligible(q):
        req=q['required']
        return {4:lambda:req[0] in killed,
                5:lambda:all(acquired[a]>=n for a,n in Counter(req).items()),
                6:lambda:all(troops[c]>=n for c,n in req) and sum(troops.values())>sum(n for c,n in req),
                7:lambda:all(a>=b for a,b in zip(resources,req)),
                8:lambda:req==(0,)}[q['mission']]()
    def pay(q):
        if q['mission']==5:
            acquired.subtract(q['required'])
        elif q['mission']==6:
            for c,n in q['required']: troops[c]-=n
        elif q['mission']==7:
            for i,n in enumerate(q['required']): resources[i]-=n
    for _ in range(400):
        seen=reachable(parsed,start,permanent|closed|alive|(guarded_events-collected),pairs)
        for cell in closed:
            o,q=gates[cell]
            key=expected_gates[o.position]['island']
            layout=report.get('layout')
            if layout:
                entry=next(i for i in layout if i['key']==key)
                island=SimpleNamespace(x=entry['center'][0],y=entry['center'][1],
                    z=entry['center'][2],radius=entry['radius'])
                bypass=bool(seen & {tuple(c) for c in entry['protected_cells']})
            else:
                island=next(i for i in ISLANDS if i.key==key)
                bypass=any(z==island.z and hypot(x-island.x,y-island.y)<6
                    and (key!='hades' or y>=72) and not parsed.terrain.tile(x,y,z).is_water
                    for x,y,z in seen)
            if bypass:
                raise ValueError(f'physical bypass into {key}')
            for c,(monster,info) in monsters.items():
                sea_ids={b['identifier'] for b in report['sea_encounters'] if b['island']==key}
                if info['identifier'] in sea_ids and adjacent(c,seen):
                    raise ValueError(f'sea trial accessible before gate: {key}')
        changed=False
        for cell in sorted(closed):
            if adjacent(cell,seen) and eligible(gates[cell][1]):
                pay(gates[cell][1]); closed.remove(cell)
                history.append('gate:'+expected_gates[gates[cell][0].position]['island'])
                changed=True; break
        if changed: continue
        for cell in sorted(alive):
            info=monsters[cell][1]
            if info['identifier'] not in avoid_battles and adjacent(cell,seen):
                killed.add(info['identifier']); alive.remove(cell)
                if info.get('artifact',65535)!=65535:acquired[info['artifact']]+=1
                for i,n in enumerate(info.get('resources',[0]*7)):resources[i]+=n
                history.append('battle:'+str(info['identifier']))
                changed=True; break
        if changed: continue
        for cell,(o,r) in rewards.items():
            # An EVENT fires only when the hero steps on its exact tile. Merely
            # reaching an adjacent shore must never award a hidden story item.
            accessible = cell in seen if o.object_id==26 else (cell[0],cell[1]+1,cell[2]) in seen
            if cell in guarded_events:
                accessible=cell not in avoid_ambushes and adjacent(cell,seen)
            if cell not in collected and accessible:
                if o.object_id==26 and (r['players']!=1 or not r['human'] or not r['once']):
                    raise ValueError('Story event will not activate exactly once for the human')
                for a,spell in r['artifacts']: acquired[a]+=1
                for c,n in r['army']: troops[c]+=n
                for i,n in enumerate(r['resources']): resources[i]+=n
                collected.add(cell); changed=True
                if r['guards']:history.append(('ambush:' if o.object_id==26 else 'cache:')+', '.join(map(str,cell)))
                for a,spell in r['artifacts']:history.append('item:'+str(a))
        if changed: continue
        for cell,(o,q) in huts.items():
            if cell not in spoken and (cell[0],cell[1]+1,cell[2]) in seen and eligible(q):
                pay(q)
                if q['reward_kind']==8:acquired[q['reward']]+=1
                elif q['reward_kind']==10:troops[q['reward'][0]]+=q['reward'][1]
                spoken.add(cell)
                history.append('quest:'+str(q['reward'])); changed=True; break
        if not changed: break
    required_huts={cell for cell,(o,q) in huts.items() if o.position not in optional_huts}
    required_alive={cell for cell in alive if monsters[cell][1]['identifier'] not in report.get('optional_monster_ids',())}
    completed_finale=finale['identifier'] in killed if finale else acquired[36]==1
    if closed or required_alive or not completed_finale or not required_huts<=spoken:
        raise ValueError(f'Progression deadlock: closed={closed}, alive={alive}, quests={len(spoken)}/{len(huts)}, inventory={acquired}, resources={resources}')
    for key in ('ismar','lotus','cyclops','aeolus','lights','giants','circe','hades','sirens','scylla','helios','calypso','phaeacia','ithaca'):
        if 'gate:'+key not in history:
            raise ValueError('Missing chapter entry')
    return dict(full_parse=True,roundtrip=True,no_early_island_access=True,no_early_sea_trials=True,
        sequential_playthrough_model=True,progression_trace=history,
        guaranteed_quest_supplies=True,all_harbours_connected_after_unlocking=True,
        model_assumptions=['Win every battle without troop losses; collect reachable supply boxes.',
                          'No flight, water walk, dimension door or external modifications.',
                          'Mixed eight-direction movement overestimates boarding possibilities.'])
