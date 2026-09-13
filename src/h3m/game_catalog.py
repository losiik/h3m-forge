"""Offline, provenance-aware game facts. No MCP dependency, game or network needed."""
from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
import json

from h3m.scenario_spec import COMBAT_SPELLS

CATEGORIES=('artifacts','creatures','spells')
RULESETS=('hota_1.8.0','hota_1.8.1')
DEFAULT_RULESET='hota_1.8.1'
FACTIONS={'castle':'Замок','rampart':'Оплот','tower':'Башня','inferno':'Инферно',
          'necropolis':'Некрополис','dungeon':'Темница','stronghold':'Цитадель',
          'fortress':'Крепость','conflux':'Сопряжение','cove':'Причал',
          'factory':'Фабрика','bulwark':'Кронверк','neutral':'Нейтральные'}


@lru_cache(maxsize=2)
def _data(ruleset=DEFAULT_RULESET):
    if ruleset not in RULESETS:raise ValueError('ruleset must be hota_1.8.0 or hota_1.8.1')
    data=json.loads(files('h3m').joinpath('data/game_catalog.json').read_text(encoding='utf-8'))
    hota=json.loads(files('h3m').joinpath('data/hota_creatures.json').read_text(encoding='utf-8'))
    for row in data['items']:row['target_ruleset']=ruleset
    data['items'].extend(hota['profiles'][ruleset])
    data['sources'].extend(hota['sources'])
    data['limitations']=hota['limitations']+data['limitations'][2:]
    data['catalog_version']='+'.join(dict.fromkeys((data['catalog_version'],hota['catalog_version'])))
    artifacts=json.loads(files('h3m').joinpath('data/artifact_catalog.json').read_text(encoding='utf-8'))
    # The complete artifact snapshot deliberately supersedes the old ten-card selection.
    data['items']=[r for r in data['items'] if r['category']!='artifacts']
    for row in artifacts['items']:
        row['target_ruleset']=ruleset
        if row['verification']['properties']=='official_documentation_and_native_data':row['reference_ruleset']=ruleset
    data['items'].extend(artifacts['items']);data['sources'].extend(artifacts['sources'])
    data['limitations']+=artifacts['limitations'];data['catalog_version']=artifacts['catalog_version']
    keys=[(r['category'],r['id']) for r in data['items']]
    if len(set(keys))!=len(keys):raise ValueError('Duplicate catalog identities')
    return data


def _category(category,optional=False):
    if category not in CATEGORIES and not(optional and category is None):
        raise ValueError('category must be artifacts, creatures or spells')


def _text(value,name,maximum):
    if value is not None and (not isinstance(value,str) or len(value)>maximum):
        raise ValueError(f'{name} must be text up to {maximum} characters')


def _normalize(value):
    return value.casefold().replace('ё','е').replace('’',"'")


def _support(row):
    category,i=row['category'],row['id']
    if category=='creatures':
        return dict(status='requires_reference_template',reason='Creature IDs are accepted; installed map templates must be present at generation time.')
    supported=(10<=i<=51 and i!=36) if category=='artifacts' else i in COMBAT_SPELLS
    return dict(status='supported' if supported else 'unsupported',
        reason='generate_scenario input contract only; does not certify combat balance or installed availability.' if supported
        else 'Current generate_scenario limits artifacts to 10..51 except 36 and spells to its combat allowlist.')


def _summary(row):
    return dict(category=row['category'],id=row['id'],key=row['key'],name_ru=row['name_ru'],name_en=row['name_en'],
        summary=row['summary'],tags=row['tags'],reference_ruleset=row['reference_ruleset'],
        target_ruleset=row['target_ruleset'],hota_runtime=row['verification']['hota_runtime'],
        scenario_support=_support(row))


def catalog_search(category=None,query=None,tag=None,faction=None,offset=0,limit=20,ruleset=DEFAULT_RULESET):
    _category(category,optional=True)
    for name,value,maximum in [('query',query,256),('tag',tag,80),('faction',faction,64)]:_text(value,name,maximum)
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=200:
        raise ValueError('offset must be >=0 and limit must be 1..200')
    data=_data(ruleset);rows=[]
    if faction is not None:
        faction=next((key for key,ru in FACTIONS.items() if _normalize(faction) in (_normalize(key),_normalize(ru))),faction)
    for row in data['items']:
        if category is not None and row['category']!=category:continue
        if faction is not None and _normalize(faction)!=_normalize((row['creature'] or {}).get('faction','')):continue
        if tag is not None and _normalize(tag) not in map(_normalize,row['tags']):continue
        if query:
            q=_normalize(query.strip())
            haystack=_normalize(' '.join([row['key'],row['name_ru'],row['name_en'],row['summary'],*row['aliases'],*row['tags']]))
            if q.isdecimal():
                if str(row['id'])!=q:continue
            elif not all(word in haystack for word in q.split()):continue
        rows.append(row)
    rows.sort(key=lambda r:(r['category'],r['id']))
    return deepcopy(dict(catalog_version=data['catalog_version'],ruleset=ruleset,items=[_summary(r) for r in rows[offset:offset+limit]],
        total=len(rows),offset=offset,next_offset=offset+limit if offset+limit<len(rows) else None,
        coverage={c:sum(r['category']==c for r in data['items']) for c in CATEGORIES},limitations=data['limitations']))


def catalog_get(category,id,ruleset=DEFAULT_RULESET):
    _category(category)
    if type(id) is not int or not 0<=id<=65534:raise ValueError('id must be integer 0..65534')
    data=_data(ruleset);row=next((r for r in data['items'] if r['category']==category and r['id']==id),None)
    item=deepcopy(row)
    if item is not None:item['scenario_support']=_support(row)
    return dict(catalog_version=data['catalog_version'],ruleset=ruleset,found=row is not None,item=item,
        sources=deepcopy([s for s in data['sources'] if row and s['id'] in row['source_ids']]),
        message='Check item.verification for source coverage; values are not a live runtime inspection.' if row else
        'Not covered by this catalog. This does not mean the entity is absent from the game; do not guess its properties.',
        limitations=deepcopy(data['limitations']))
