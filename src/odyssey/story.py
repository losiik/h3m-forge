"""A chronological, quest-linked sea adaptation of Homer's Odyssey."""
from collections import Counter, deque
from dataclasses import dataclass
from math import hypot, sin, cos
from random import Random

from h3m import catalog, conditions, hota, mapfile, options
from h3m.build import sign_payload
from h3m.terrain import Terrain, TerrainMap
from h3m.stream import BinaryReader
from h3m.world import Placement, _walk, _route, scenery_for
from odyssey import payloads as p
from odyssey.navigation import harbours, build_barriers, validate_progression


@dataclass(frozen=True)
class Island:
    key: str
    name: str
    x: int
    y: int
    terrain: Terrain = Terrain.GRASS
    radius: int = 10
    z: int = 0


ISLANDS = (
    Island('troy', 'Троя', 22, 112, Terrain.DIRT, 12),
    Island('ismar', 'Исмар: киконы', 18, 76),
    Island('lotus', 'Лотофаги', 20, 36, Terrain.SAND),
    Island('cyclops', 'Пещера Полифема', 50, 18, Terrain.ROUGH),
    Island('aeolus', 'Эолия', 88, 18, Terrain.HIGHLANDS),
    Island('giants', 'Лестригоны', 124, 36, Terrain.WASTELAND),
    Island('circe', 'Ээя: Кирка', 124, 74, Terrain.GRASS, 12),
    Island('sirens', 'Сирены', 122, 112, Terrain.SAND),
    Island('scylla', 'Сцилла и Харибда', 90, 122, Terrain.ROUGH),
    Island('helios', 'Тринакрия: стада Гелиоса', 54, 124, Terrain.GRASS, 10),
    Island('calypso', 'Огигия: Калипсо', 54, 82, Terrain.GRASS),
    Island('phaeacia', 'Схерия: феаки', 90, 84, Terrain.GRASS),
    Island('ithaca', 'Итака', 72, 54, Terrain.GRASS, 12),
    Island('lights', 'Огни Итаки: морская стоянка', 102, 50, Terrain.SAND, 6),
    Island('hades', 'Царство теней: Тиресий', 124, 74, Terrain.SUBTERRANEAN, 12, 1),
)


# Entry guards consume chapter signs; on revisits the next seer consumes them.
# No random artifact source is placed.
CHAPTERS = (
    ('ismar', 7, 8, (40,), '01. Исмар',
     'После победы над Троей спутники разграбили Исмар и не послушали приказа отплыть. Киконы собирают подкрепления. Разбейте отряд у восточной дороги и принесите его трофей. Знак похода уже передан хранителю пролива.',
     'Киконы отброшены, но промедление стоило людям жизни. Держите курс на север, к лотофагам (20,36).'),
    ('lotus', 8, 9, (), '02. Лотос забвения',
     'Лотофаги мирны. Их плод заставляет забыть дом. Вернитесь за тремя посланцами: убедить их уже нельзя. Одиссею предстоит силой увести товарищей к кораблю.',
     'Вы связали забывших Итаку спутников и увезли их. Ни один больше не попробует лотоса. На северо-востоке — пещера циклопа (50,18).'),
    ('cyclops', 9, 10, (41,), '03. Никто',
     'Полифем запер людей в пещере. Убить его нельзя: никто не сдвинет камень у входа. В соседней хижине подготовьте вино и кол; затем принесите знак спасения.',
     '«Меня зовут Никто». Опьяневший Полифем ослеплён; люди выходят под брюхом баранов. Но вы выкрикнули своё имя, и циклоп призвал месть Посейдона. Плывите на восток, к Эолу (88,18).'),
    ('aeolus', 10, 11, (), '04. Мех Эола',
     'Первая буря Посейдона позади. Эол отдаёт Одиссею мех с запертыми ветрами. Итака уже близка, но испытание доверием ещё впереди.',
     'Девять дней попутный ветер несёт корабль к дому. На десятый видны огни Итаки. Плывите к морской стоянке (102,50). Дом так близок — но проход к самой Итаке ещё закрыт.'),
    ('lights', 11, 22, (), '05. Огни родины',
     'Вы уже различаете огни Итаки и наконец засыпаете у руля. Спутники решают, что Эол подарил царю золото. Одиссею предстоит пережить раскрытие меха. Эта стоянка представляет корабль у берегов, а не возвращение во дворец.',
     'Мех раскрыт. Вырвавшиеся ветры уносят корабль от дома. Вернитесь к Эолу (88,18), теперь в восточную хижину: попросите помощи ещё раз.'),
    ('aeolus', 22, 21, (), '06. Отказ Эола',
     'Второй разговор с Эолом откроется лишь после сцены у огней Итаки. Принесите знак раскрытого меха в восточную хижину.',
     'Эол отказывает: нельзя помогать тому, кого ненавидят боги. Снова поднимайте парус, теперь без подаренного ветра. Впереди гавань лестригонов на юго-востоке (124,36).'),
    ('giants', 21, 12, (42,), '06. Гавань великанов',
     'Лестригоны забрасывают гавань скалами и пожирают моряков. Ваш корабль остался снаружи. Отбейте великанов у берега и принесите трофей.',
     'Из всей флотилии спасается один корабль. Южнее лежит остров Кирки — Ээя (124,74).'),
    ('circe', 12, 13, (), '07. Чары Кирки',
     'Кирка обратила разведчиков в свиней. Гермес вручает вам молю: её зелье не возьмёт вас. Одиссей требует клятву не причинять ему вреда.',
     'Кирка снимает чары. После года на Ээе вы просите отпустить вас. Сначала нужно спросить умершего Тиресия. Врата царства теней стоят на северной стороне острова.'),
    ('hades', 13, 14, (), '08. Тиресий',
     'Тени сходятся к жертвенной яме. Знак Кирки передан хранителю: теперь выслушайте Тиресия. С мёртвыми здесь не сражаются.',
     '«Не трогайте стад Гелиоса. Если погубите их, домой вернётесь один, поздно, на чужом корабле». Вы встречаете тень матери и узнаёте о верности Пенелопы. Вернитесь через врата к Кирке, в восточную хижину.'),
    ('circe', 14, 15, (), '09. Последний совет Кирки',
     'Этот разговор откроется после возвращения от Тиресия. Принесите его знак в восточную хижину Кирки.',
     'Залепите уши гребцам воском, а себя велите привязать к мачте. У Сциллы держитесь скалы: потерять шестерых страшно, но Харибда поглотит всех. Плывите на юг, к сиренам (122,112).'),
    ('sirens', 15, 16, (), '10. Песня сирен',
     'Исполните совет Кирки: воск для гребцов, путы для царя. Прикажете развязать — пусть затянут узлы ещё крепче. Нимфы в проливе уже побеждены; саму песню сирен переживают без боя.',
     'Вы услышали песню и рвались за борт, но спутники не нарушили приказа. Корабль миновал сирен без потерь. На юго-западе — Сцилла (90,122). Берегите шесть копейщиков для следующего испытания.'),
    ('scylla', 16, 17, (43,), '11. Шесть голосов',
     'Харибда втягивает море; Сцилла нависает над узким проходом. В соседней хижине отдайте шесть копейщиков — цену спасения корабля. Здесь нельзя победить чудовище силой.',
     'Шесть спутников исчезли в пастях Сциллы. Вы слышали, как они звали вас по имени. Уцелевшие требуют отдыха. Плывите на запад к Тринакрии (54,124).'),
    ('helios', 17, 18, (44,), '12. Стада Солнца',
     'Ветры держат корабль на Тринакрии. Припасы иссякли. Пока вы молились, Еврилох убедил спутников нарушить запрет. Бой со священным стадом у восточного берега изображает их роковой выбор. Принесите трофей.',
     'Гелиос требует кары. Зевс раскалывает корабль молнией, и пророчество сбывается: все прежние спутники погибают. На обломке киля Одиссей достигает Огигии (54,82). В игровой армии отныне представлены новые спутники и помощь богов; численность автоматически не обнуляется.'),
    ('calypso', 18, 19, (), '13. Семь лет на Огигии',
     'Калипсо предлагает бессмертие, но Одиссей тоскует по Итаке. Семь лет здесь проходят одной сценой, без ожидания игровых лет.',
     'Гермес приносит волю Зевса: отпустить Одиссея. Калипсо помогает построить плот. Посейдон разбивает его, но покрывало Ино спасает вас. Восточнее лежит Схерия (90,84).'),
    ('phaeacia', 19, 20, (), '14. Рассказ у Алкиноя',
     'Навсикая приводит вас к феакам. На пиру песнь Демодока о Трое вызывает слёзы. Откройте своё имя хозяевам.',
     'Вы рассказали Алкиною свои странствия. Феаки обещают доставить вас домой спящим и оставляют дары. Итака на северо-западе (72,54). Там Афина скроет вас под видом нищего.'),
    ('ithaca', 20, 36, (45,), '15. Ложе оливы',
     'Знак феаков открыл пролив Итаки. Эвмей укрывает странника, Телемах узнаёт отца. Женихи пируют в вашем доме. Разбейте их отряд у дворца, верните трофей Пенелопе в западную хижину. Лишь пройденный путь и освобождённый дом завершат историю.',
     'Вы натянули лук и покарали женихов. Пенелопа велит вынести брачное ложе. «Оно выросло из живой оливы — его нельзя сдвинуть!» Только вы двое знаете эту тайну. Она узнаёт мужа. Афина останавливает месть родичей: после двадцати лет Одиссей дома.'),
)

# Keep chapter numbers stable when an episode gains a playable intermediate scene.
CHAPTERS = tuple((*row[:4], f'{i:02}. '+row[4].split('. ',1)[1], *row[5:])
                 for i,row in enumerate(CHAPTERS,1))


def terrain_map(seed):
    size = 144
    data = bytearray(bytes([Terrain.WATER, 0, 0, 0, 0, 0, 0]) * size**2
                     + bytes([Terrain.ROCK, 0, 0, 0, 0, 0, 0]) * size**2)
    for i, island in enumerate(ISLANDS):
        for y in range(2, size-2, 2):
            for x in range(2, size-2, 2):
                distance = hypot((x-island.x)*.94, (y-island.y)*1.06)
                edge = island.radius + 1.2*sin(x*.25+i)*cos(y*.21+i)
                if distance > edge+2:
                    continue
                t = island.terrain if distance < edge-2 or island.z else Terrain.SAND
                for dy in range(2):
                    for dx in range(2):
                        data[((island.z*size+y+dy)*size+x+dx)*7] = t
    return TerrainMap(bytes(data), size, 2)


def generate(assets, seed=20260905):
    result = hota.new_map('Одиссея: гнев Посейдона',
        'Одиночное сюжетное приключение по Гомеру. От Трои через острова и царство теней к Пенелопе. '
        'Сюжетные проливы и морские испытания. Цель — 2–4 часа, сложность 100%. Знаки открывают проливы; '
        'не продавайте их. Победа — узнавание у Пенелопы. Потеря Одиссея — поражение. '
        'Годы сжаты до сцен; армия после кораблекрушения условна.',
        size=144, two_levels=True, players=1, seed=seed)
    result.terrain = terrain_map(seed)
    assets.terrain.apply(result.terrain, seed=seed)
    player = result.players[0]
    player.can_computer_play = 0
    player.allowed_factions = 1
    player.is_faction_random = 0
    # No tavern heroes and no random spell source: one protagonist, no shortcuts.
    result.meta.allowed_heroes = options.SizedMask(bytes(27), 215)
    result.meta.allowed_spells = bytes([255])*9
    # Artifact victory requires this flag in the native editor. Heroes ignores
    # elimination victory when the scenario has exactly one playable player.
    # See CMapLoaderH3M::readVictoryLossConditions (VCMI, matching H3 behavior).
    result.victory = conditions.VictoryCondition(conditions.VictoryType.ARTIFACT, 1, 0, p.pack('H', 36))
    result.loss = conditions.LossCondition(conditions.LossType.LOSE_HERO, bytes([22, 117, 0]))
    reserved = set()
    placement = Placement(result, reserved)
    sites, records, challenge_records = {}, [], []
    docks = harbours(result, ISLANDS)
    islands = {i.key: i for i in ISLANDS}

    # Broad central lanes, with a southern beach connection on every island.
    for island in ISLANDS:
        for y in range(island.y-6, island.y+island.radius+5):
            for x in range(island.x-1, island.x+2):
                cell = (x, y, island.z)
                if result.terrain.tile(*cell).terrain not in (Terrain.WATER, Terrain.ROCK):
                    reserved.add(cell)
        if island.z == 0:
            reserved.update(_route(result.terrain,(island.x,island.y,0),docks[island.key]))
            if island.key == 'troy':
                x,y,z = docks[island.key]
                boat = (x+1,y+1,z)
                catalog.place(result,catalog.BorrowedObject(assets.get(8,0),b'','native'),*boat)
                placement.occupied.add((x,y+1,z))

    def put(kind, center, payload=b'', sub=0, label=None, radius=8):
        template = assets.get(kind, sub, terrain=result.terrain.tile(*center).terrain)
        placement.near(template, center, payload, radius=radius)
        obj = result.objects[-1]
        if label:
            sites[label] = (obj.x, obj.y, obj.z)
        return obj

    def sign(center, text):
        return put(91, center, sign_payload(text.encode('cp1251')))

    # Explicit hero position must match the loss condition.
    hero_template = assets.get(34, 0)
    hero_pos = (23, 117, 0)
    hero_cells = placement.cells(hero_template, hero_pos)
    reserved.difference_update(hero_cells)
    placement.place(hero_template, hero_pos, p.hero(), interactive=True)
    sites['Одиссей'] = hero_pos
    town = put(98, (25, 109, 0), p.town('Ахейская стоянка', 0), label='Ахейская стоянка')
    player.has_main_town = 1
    player.main_town_pos = (town.x-2, town.y, town.z)
    player.generate_hero_at_main_town = 0
    sign((18, 119, 0), 'ОДИССЕЯ. Начало: севернее, в Исмаре (18,76). '
         'Берите дары в ящиках, читайте таблички и посещайте провидцев. '
         'Знаки глав открывают проливы в рифах. Переданный стражу знак исчезает и больше не нужен хижине на острове. '
         'Открытые проливы остаются открытыми для возвращения. Ваш корабль стоит у южного пляжа; сохраняйте его. '
         'Координаты в подсказках отсчитываются от нуля. '
         'Шесть копейщиков понадобятся у Сциллы. Стоянка у Трои сохраняет ваше владение на время плавания.')
    put(6, (27, 117, 0), p.box('Припасы ахейцев. Двенадцать копейщиков — ваши ближайшие спутники. '
        'Сохраните хотя бы шестерых до Сциллы; запасной отряд ждёт у неё на берегу.',
        resources=(20, 0, 10, 0, 0, 0, 8000)))

    visited_islands = set()
    for index, (key, previous, reward, trophies, title, first, done) in enumerate(CHAPTERS):
        island = islands[key]
        side = 5 if (key, reward) in {('circe',15),('aeolus',21)} else (-2 if key=='lights' else -4)
        pos = (island.x+side, island.y, island.z)
        needs_entry = key not in visited_islands
        required = tuple(trophies) if needs_entry else (previous,*trophies)
        mission = 5 if required else 8
        required = required or (0,)
        obj = put(83, pos, p.seer(required, reward, title+'\n\n'+first, done,mission=mission), label=title)
        records.append(dict(title=title, island=key, required=list(required), mission=mission,
                            entry_required=previous if needs_entry else None, reward=reward,
                            position=[obj.x, obj.y, obj.z], first=first, done=done))
        visited_islands.add(key)
        sign((island.x-3, island.y+(3 if key=='lights' else 6), island.z), title+'\n'+first)

    def battle(key, creature, count, trophy, message):
        island = islands[key]
        obj = put(54, (island.x+5, island.y+3, island.z),
                  p.monster(30000+trophy, count, message, trophy), sub=creature,
                  label='battle_'+key)
        challenge_records.append(dict(kind='battle', island=key, reward=trophy,
                                      creature=creature, count=count, position=[obj.x, obj.y, obj.z]))

    battle('ismar', 1, 45, 40, 'Киконы контратакуют. Прикройте отступление к кораблю!')
    battle('giants', 94, 7, 42, 'Великаны бросают камни в корабли. Пробейте выход для единственного уцелевшего судна!')
    battle('helios', 102, 16, 44, 'Священные стада Гелиоса. Это запретный бой: он изображает неповиновение голодных спутников и ведёт к кораблекрушению.')
    battle('ithaca', 7, 65, 45, 'Женихи занимают ваш дом. Телемах запер двери. Пришла пора натянуть лук Одиссея!')

    obj = put(83, (55, 23, 0), p.seer((10, 0, 0, 0, 0, 0, 1000), 41,
        'План «Никто»: отдайте 10 дерева для заострённого кола и 1000 золота за крепкое вино Марона. '
        'Напоите Полифема, ослепите его и спрячьтесь под баранами. Не убивайте циклопа.',
        'Кол раскалён, Полифем пьян. Вместо боя вы готовите побег. Верните знак спасения в западную хижину.', mission=7))
    challenge_records.append(dict(kind='resources', reward=41, required=[10,0,0,0,0,0,1000], position=[obj.x,obj.y,obj.z]))
    obj = put(83, (95, 129, 0), p.seer(((0, 6),), 43,
        'Путь мимо Сциллы стоит шести копейщиков. Передайте ровно шестерых спутников: они будут потеряны навсегда, но корабль избежит Харибды.',
        'Сцилла похитила шестерых. Знак этой жертвы позволит продолжить путь в западной хижине.', mission=6))
    challenge_records.append(dict(kind='army', reward=43, required=[[0,6]], position=[obj.x,obj.y,obj.z]))
    put(6, (86, 131, 0), p.box('Шестеро моряков переходят с вёсел в ваш отряд. Это запас копейщиков для неизбежной жертвы Сцилле.', army=((0,6),)))

    # Surface and underground gates occupy exactly matching coordinates.
    gate_template = assets.get(103, 0)
    gate_pos = (128, 68)
    for z in (0, 1):
        placement.place(gate_template, (*gate_pos, z), interactive=True)
    sites['Врата Тиресия'] = (*gate_pos, 0)
    put(98, (77, 49, 0), p.town('Дворец Одиссея'), label='Дворец Одиссея')
    for key in ('aeolus', 'circe', 'calypso', 'phaeacia'):
        island = islands[key]
        put(6, (island.x+5, island.y+7, 0), p.box(
            'Союзники дают провиант и людей для дальнейшего пути. Это игровое пополнение; годы странствий сжаты.',
            army=((3,20),(6,15)), resources=(5,0,0,0,0,0,3000), experience=2000))

    locks,sea_trials,reef_count = build_barriers(result,assets,ISLANDS,CHAPTERS,docks,placement)

    # Decorate outside reserved routes and generous clearings around the story.
    rng = Random(seed)
    palettes = {t: scenery_for(assets, t) for t in Terrain}
    points = [(x,y,i.z) for i in ISLANDS for y in range(i.y-i.radius-1,i.y+i.radius+2)
              for x in range(i.x-i.radius-1,i.x+i.radius+2)]
    rng.shuffle(points)
    decoration_count = 0
    for pos in points:
        if rng.random() > .24:
            continue
        choices = palettes[result.terrain.tile(*pos).terrain]
        if not choices:
            continue
        if any(pos[2] == obj.z and hypot(pos[0]-obj.x, pos[1]-obj.y) < 2.8
               for obj in result.objects if obj.object_id < 114 or obj.object_id > 140):
            continue
        t = rng.choice(choices)
        if placement.fits(t, pos):
            placement.place(t, pos)
            decoration_count += 1

    report = validate(result, records, challenge_records, docks, placement)
    report.update(validate_progression(result,records,challenge_records,locks,sea_trials))
    report.update(seed=seed, name=result.header.name.decode('cp1251'), chapters=records,
                  navigation_revision=2,harbour_guards=locks,sea_encounters=sea_trials,
                  reefs=reef_count,sea_battles=len(sea_trials),total_battles=4+len(sea_trials),
                  challenges=challenge_records, sites=sites, decorations=decoration_count,
                  islands=[dict(key=i.key,name=i.name,center=[i.x,i.y,i.z]) for i in ISLANDS],
                  estimated_hours='2–4; needs full human playtest',
                  adaptations=['Chronological retelling, rather than the poem’s frame narrative.',
                               'Years and shipwrecks are narrated; existing army is not cleared.',
                               'Aeolus episode requires sailing to the coast of Ithaca and back to Aeolus.',
                               'Classic artifacts represent chapter signs; their game names are retained.'])
    return result, report


def validate(result, chapters, challenges, docks, placement):
    # Structural parsing alone cannot establish playability; check quest supply
    # and conservative paths independently, then validate with the native editor.
    raw = mapfile.serialize(result)
    parsed = mapfile.parse(raw)
    if parsed.stopped_at or len(parsed.objects) != len(result.objects):
        raise ValueError(f'native parse failed: {parsed.stopped_at}')
    # Inspect the serialized quests, not just their design metadata.
    huts = {(o.x,o.y,o.z):o for o in parsed.objects if o.object_id == 83}
    rewards = Counter()
    for record in [*chapters, *challenges]:
        if record.get('kind') == 'battle':
            continue
        reader = BinaryReader(huts[tuple(record['position'])].payload)
        if reader.u32() != 1:
            raise ValueError('expected one nonrepeatable quest')
        mission = reader.u8()
        if mission == 5:
            required = []
            for _ in range(reader.u8()):
                required.append(reader.u16())
                if reader.u16() != 0:
                    raise ValueError('noncanonical native artifact field')
            if required != record['required']:
                raise ValueError('serialized quest differs from story chain')
        elif mission == 6:
            required = [[reader.u16(),reader.u16()] for _ in range(reader.u8())]
            if required != record['required']:
                raise ValueError('serialized troop sacrifice differs')
        elif mission == 7:
            if [reader.u32() for _ in range(7)] != record['required']:
                raise ValueError('serialized resource cost differs')
        elif mission == 8:
            if reader.u8() != record['required'][0]:
                raise ValueError('serialized hero requirement differs')
        else:
            raise ValueError('unexpected story quest')
        if reader.u32() != 0xffffffff:
            raise ValueError('unexpected quest deadline')
        for _ in range(3):
            reader.string()
        if reader.u8() != 8 or reader.u16() != record['reward'] or reader.u16() != 0:
            raise ValueError('serialized quest reward differs')
        if reader.u32() != 0 or reader.bytes_(2) != bytes(2):
            raise ValueError('unexpected repeatable quest')
        rewards[record['reward']] += 1
    if rewards[36] != 1:
        raise ValueError('victory must have exactly one reward source')
    inventory = Counter({7:1})
    inventory.update(c['reward'] for c in challenges)
    for chapter in chapters:
        required = ([chapter['entry_required']] if chapter['entry_required'] is not None else [])
        if chapter['mission']==5:
            required += chapter['required']
        for item in required:
            if inventory[item] != 1:
                raise ValueError(f'quest supply broken at {chapter["title"]}: {item}')
            inventory[item] -= 1
        inventory[chapter['reward']] += 1
    if inventory[36] != 1:
        raise ValueError('victory artifact is unreachable')
    blocked = set()
    for obj in result.objects:
        t = result.object_templates[obj.template_index]
        visits = set(t.visitable_cells())
        blocked.update((obj.x+dx,obj.y+dy,obj.z) for dx,dy in t.blocked_cells() if (dx,dy) not in visits)
    failures = []
    for island in ISLANDS:
        start = docks.get(island.key, (127,69,1))
        reached = _walk(result.terrain, start, blocked)
        for obj in result.objects:
            if obj.z != island.z or hypot(obj.x-island.x,obj.y-island.y)>island.radius+5:
                continue
            t = result.object_templates[obj.template_index]
            if obj.object_id == 8 or any(result.terrain.tile(obj.x+dx,obj.y+dy,obj.z).is_water
                                        for dx,dy in t.visitable_cells()):
                continue
            for dx,dy in t.visitable_cells():
                cell = (obj.x+dx,obj.y+dy,obj.z)
                if cell not in reached:
                    failures.append([obj.object_id,list(cell)])
    if failures:
        raise ValueError(f'unreachable story objects: {failures}')
    # All ships and beach landings share the same sea, with no enclosed ponds.
    sea = set()
    queue = deque([(0,0)])
    while queue:
        x,y = queue.popleft()
        if (x,y) in sea:
            continue
        sea.add((x,y))
        for xx,yy in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if 0 <= xx < 144 and 0 <= yy < 144 and (xx,yy) not in sea and result.terrain.tile(xx,yy,0).is_water:
                queue.append((xx,yy))
    for x,y,z in docks.values():
        if (x,y+1) not in sea:
            raise ValueError('isolated harbour')
    return dict(native_revision=9, size=144, levels=2, objects=len(result.objects),
                quest_chain_valid=True, all_story_objects_accessible=True,
                sea_terrain_connected=True, native_editor_checked=False, full_playtest=False)
