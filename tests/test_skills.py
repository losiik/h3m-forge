import struct
from types import SimpleNamespace

import pytest

from h3m import hota, mapfile
from h3m.heroes import PredefinedHero
from h3m.skills import skill_catalog, inspect_hero_skills, describe_skills, validate_skill_pairs


def test_catalog_distinguishes_all_magic_schools_and_mastery():
    rows=skill_catalog()['items']
    assert len(rows)==28 and len({r['key'] for r in rows})==28
    # Independent expectations from the native skill table, not the enum.
    assert [(rows[i]['key'],rows[i]['name_ru']) for i in (14,15,16,17)]==[
        ('fire_magic','Магия огня'),('air_magic','Магия воздуха'),
        ('water_magic','Магия воды'),('earth_magic','Магия земли')]
    for query in ('17','EARTH','earth_magic','земля','ЗЕМЛИ'):
        assert [r['id'] for r in skill_catalog(query)['items']]==[17]
    assert skill_catalog('unknown')['items']==[]
    assert skill_catalog()['levels'][2]==dict(value=2,key='advanced',name_ru='Продвинутый')


@pytest.mark.parametrize('pairs', [[[17,0]],[[17,4]],[[29,2]],[[True,2]],[[17,True]],
                                  [[17,1],[17,2]],[[17]],list(zip(range(9),[1]*9))])
def test_invalid_assignments_rejected(pairs):
    with pytest.raises(ValueError,match='hero_skills'):validate_skill_pairs(pairs)


def test_skill_effect_prerequisites_do_not_confuse_fire_with_earth():
    assert describe_skills([(14,3)])['permanent_resurrection_skill_ready'] is False
    assert describe_skills([(17,1)])['permanent_resurrection_skill_ready'] is False
    assert describe_skills([(17,2),(7,2)])['permanent_resurrection_skill_ready'] is True
    assert describe_skills(None)['skills'] is None
    assert describe_skills([])['skills']==[]
    unknown=describe_skills([(250,2)])
    assert not unknown['skills'][0]['known'] and unknown['skills'][0]['name_ru'] is None
    assert unknown['issues'] and unknown['permanent_resurrection_skill_ready'] is None
    assert describe_skills([(17,2),(17,1)])['issues']


@pytest.mark.parametrize('ab,sod',[(False,False),(True,False),(True,True)])
def test_legacy_and_modern_hero_prefix_and_inheritance(ab,sod):
    # Independent byte fixture, no authored.hero / skill enum shared with reader.
    prefix=(struct.pack('<I',123) if ab else b'')+bytes([0,9,0])
    prefix+=(bytes([1]) if sod else b'')+struct.pack('<I',830)+bytes([0])
    objects=[SimpleNamespace(object_id=34,position=(4,5,0),payload=prefix+bytes([1])+struct.pack('<I',2)+bytes([14,3,17,2])),
             SimpleNamespace(object_id=62,position=(6,5,0),payload=prefix+bytes([0])),
             SimpleNamespace(object_id=70,position=(7,5,0),payload=prefix+bytes([0])),
             SimpleNamespace(object_id=34,position=(8,5,0),payload=prefix+bytes([1])+struct.pack('<I',0))]
    m=SimpleNamespace(objects=objects,header=SimpleNamespace(features=SimpleNamespace(is_ab_or_later=ab,is_sod_or_later=sod)),
        predefined_heroes=SimpleNamespace(heroes={9:PredefinedHero(9,secondary_skills=bytes([7,2,17,3]))}),stopped_at=None,tail=b'')
    rows=inspect_hero_skills(m)['items']
    assert rows[0]['skills'][0]['key']=='fire_magic' and rows[0]['skills'][1]['key']=='earth_magic'
    assert rows[0]['skills_source']=='object'
    assert rows[1]['skills_source']=='predefined_hero' and rows[1]['skills'][1]['level']==3
    assert rows[2]['skills'] is None and rows[2]['skills_source']=='game_defaults_unresolved'
    assert rows[3]['skills']==[] and rows[3]['skills_source']=='object'
    assert rows[4]['scope']=='predefined'
    objects[0].payload=b''
    result=inspect_hero_skills(m)
    assert result['errors'] and result['items'][0]['skills'] is None


def test_service_reads_saved_native_payload_without_changes(tmp_path):
    from h3m.authored import hero
    from h3m.objects import ObjectTemplate
    from h3m.instances import ObjectInstance
    from h3m.service import MapService
    m=hota.new_map('Навыки')
    m.object_templates.append(ObjectTemplate(b'TEST.def',bytes([255])*6,bytes(6),0,256,34,0,0,0,bytes(16)))
    m.objects.append(ObjectInstance(4,5,0,0,bytes(5),hero(name='Проверка',skills=((14,1),(17,2),(7,2))),34))
    path=tmp_path/'skills.h3m';mapfile.save(path,m);original=path.read_bytes()
    service=MapService(tmp_path,tmp_path/'no-game')
    r=service.inspect_hero_skills(str(path),limit=1)
    assert r['full_parse'] and not r['errors'] and r['total']==1
    assert r['items'][0]['permanent_resurrection_skill_ready']
    assert [s['name_ru'] for s in r['items'][0]['skills']]==['Магия огня','Магия земли','Мудрость']
    assert service.inspect_hero_skills(str(path),offset=1)['items']==[]
    assert service.skill_catalog('17')['items'][0]['key']=='earth_magic'
    assert path.read_bytes()==original
