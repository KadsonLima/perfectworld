"""Starting loadout of every class: the templates (roles 16-31) copied by
gamedbd when a character is created, exported to its clsconfig table.

Each of the 12 real templates gets level 100 with the status points spent on
the set requirements (rest in vitality), every normal trainer skill at its
maximum level (capped at 10, sage/demon versions excluded), the ★★ Nirvana
weapon and 6-piece armor set +12 with stones equipped, and HP/MP charms in the
inventory. The 4 empty templates of gender-locked classes are left untouched.

Native exportrole fails on templates because they have no task record, so the
export uses a copy of gamedbd whose ExportRole skips that table (patched copy,
never used by the server). Import and exportclsconfig use the original binary.

  --scratch  runs the whole pipeline on a throwaway copy of the gamedbd volume
  --apply    stops the game services, backs up the database and applies
"""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
import struct
import subprocess
import time
import xml.etree.ElementTree as ET

from edit_nirvana import ROOT, command, compose, variable, value, addon, catalog, validate_data

TEMPLATES = range(16, 32)
CLASS_NAMES = ['Blademaster','Wizard','Psychic','Venomancer','Barbarian','Assassin',
               'Archer','Cleric','Seeker','Mystic','Duskblade','Stormbringer']
# Equipment slot: helm 1, cape 3, body 4, legs 6, feet 7, wrists 8 (weapon 0).
ARMOR = {'heavy':{1:25685,3:25700,4:25687,6:25686,7:25683,8:25684},    # Cascade Glow
         'light':{1:25690,3:25699,4:25692,6:25691,7:25688,8:25689},    # Myriad Blossom
         'arcane':{1:25695,3:25698,4:25697,6:25696,7:25693,8:25694}}   # Dragon Rise
CLASSES = {0:('heavy',25653),   # ★★Unicorn's Tragedy
           1:('arcane',25678),  # ★★Glaive of Nirvana
           2:('arcane',26062),  # ★★Buddha's Hatred
           3:('arcane',25678),
           4:('heavy',25655),   # ★★Resonance of Pride
           5:('light',26054),   # ★★Netherworld Guidance
           6:('light',25665),   # ★★Jaden Emperor's Defiance
           7:('arcane',25676),  # ★★Sandy World
           8:('heavy',25645),   # ★★Autumn Cresent
           9:('arcane',25672),  # ★★Foundation of World
           10:('light',44935),  # ★★Streak of Sorrow
           11:('arcane',45018)} # ★★Dent of Destiny
WEAPON_STONE, ARMOR_STONE = 38154, 38155  # Devil Stone ATK LV +3, Serenity Stone DEF LV +3
HP_CHARM, MP_CHARM = 46967, 46966         # Ruby Guardian Charm, Ruby Spirit Charm
LEVEL, REFINE, SKILL_LEVEL = 100, 12, 10
SAGE_DEMON_RANKS = {20,21,22,30,31,32}
REFINE_FACTOR = 37.5  # +12 multiplier of the refine table in gs

def sha256(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def export_binary():
    """Copy of runtime/inspect/gamedbd with ExportRole jumping over the task lookup."""
    source=ROOT/'runtime/inspect/gamedbd';target=ROOT/'runtime/inspect/gamedbd-export-templates'
    data=bytearray(source.read_bytes())
    at,to,offset=0x8266f80,0x826707b,0x21ef80  # file offset of `at` in the text segment
    assert data[offset:offset+5]==bytes.fromhex('83ec088d85'),'Unexpected gamedbd build'
    data[offset:offset+5]=b'\xe9'+struct.pack('<i',to-(at+5))
    target.write_bytes(data)
    return target

def load():
    server,client=catalog()
    extra=json.loads((ROOT/'runtime/inspect/class-template-data.json').read_text(encoding='utf-8'))
    for kind in ('AUTOHP_ESSENCE','AUTOMP_ESSENCE','CHARRACTER_CLASS_CONFIG'):
        server[kind]={r['ID']:r for r in extra[kind]}
    return server,client,extra

def class_skills(extra,cls):
    skills=extra['SKILLS'];taught=set()
    for service in extra['NPC_SKILL_SERVICE']:
        taught.update(v for k,v in service.items() if k.startswith('id_skills') and v)
    return sorted((sid,min(SKILL_LEVEL,skills[str(sid)]['max_level'])) for sid in taught
                  if skills[str(sid)]['cls']==cls and skills[str(sid)]['rank'] not in SAGE_DEMON_RANKS)

def sockets(r,count):
    probabilities=[max(r[f'drop_probability_socket{i}'],r[f'make_probability_socket{i}']) for i in range(count)]
    return max(i for i,p in enumerate(probabilities) if p>0)

def equipment_data(r,kind,server):
    dur=r['durability_max']*100  # elements store durability/100, see the native templates
    header=struct.pack('<6H2I',r['require_level'],r['character_combo_id'],r['require_strength'],
                       r['require_tili'],r['require_agility'],r['require_energy'],dur,dur)
    if kind=='WEAPON_ESSENCE':
        sub=server['WEAPON_SUB_TYPE'][r['id_sub_type']]
        speeds=[sub[f'probability_{s}'] for s in ('fastest','fast','normal','slow','slowest')]
        # generate_weapon: interval = int(attack_speed*20+0.1) + speed index - 2.
        ticks=int(sub['attack_speed']*20+0.10000000149011612)+next(i for i,p in enumerate(speeds) if p>0)-2
        weapon_type={1:0,2:2}.get(r['short_range_mode'],1)  # ranged weapons are type 1
        essence=struct.pack('<2h8i2f',weapon_type,0,r['id_major_type'],r['level'],r['require_projectile'],
                            r['damage_low'],r['damage_high_max'],r['magic_damage_low'],r['magic_damage_high_max'],
                            ticks,r['attack_range'],sub['attack_short_range'])
        holes=[WEAPON_STONE]*sockets(r,3);stone_addon='id_addon_damage'
    else:
        essence=struct.pack('<9i',r['defence_high'],r['armor_enhance_high'],r['mp_enhance_high'],
                            r['hp_enhance_high'],*[r[f'magic_defences_{i}_high'] for i in range(1,6)])
        holes=[ARMOR_STONE]*sockets(r,5);stone_addon='id_addon_defence'
    aid=r['levelup_addon']
    bonuses=[addon(aid,int(server['EQUIPMENT_ADDON'][aid]['param1']*REFINE_FACTOR),REFINE)]
    for stone_id in holes:
        aid=server['STONE_ESSENCE'][stone_id][stone_addon]
        bonuses.append(addon(aid,server['EQUIPMENT_ADDON'][aid]['param1'],stone=True))
    data=(header+struct.pack('<HBB',len(essence),3,0)+essence+struct.pack('<I',len(holes))+
          b''.join(struct.pack('<I',s) for s in holes)+struct.pack('<I',len(bonuses))+b''.join(bonuses)).hex()
    validate_data(data,kind)
    return data,len(holes)

def item(parent,fields,tag):
    node=ET.Element(tag)
    for name,v in fields.items():
        ET.SubElement(node,'variable',name=name,type='Octets' if name=='data' else 'int').text=str(v)
    reserved=parent.find("variable[@name='reserved1']")
    # Keep native XML ordering: items precede the reserved variables.
    if reserved is None:parent.append(node)
    else:parent.insert(list(parent).index(reserved),node)

def prepare(xml,server,client,extra):
    root=ET.fromstring(xml);base=root.find('base');status=root.find('status')
    rid=int(value(base,'id'));cls=int(value(base,'cls'))
    assert rid in TEMPLATES and int(value(status,'level'))==1
    armor,weapon_id=CLASSES[cls]
    pieces=[(0,weapon_id,'WEAPON_ESSENCE')]+[(pos,i,'ARMOR_ESSENCE') for pos,i in ARMOR[armor].items()]
    records=[]
    for pos,item_id,kind in pieces:
        r=server[kind][item_id];c=client[kind][item_id]
        for key,v in r.items():
            if key in c and isinstance(v,(int,float)):assert v==c[key],f'Catalog mismatch {item_id}: {key}'
        assert r['character_combo_id']>>cls&1 and r['require_level']<=LEVEL,f'{item_id} unusable by class {cls}'
        records.append((pos,item_id,kind,r))
    # Status points: 5 per stat at level 1 plus 5 per level; spend the requirements, rest in vitality.
    need=lambda key:max([5]+[r[key] for *_,r in records])
    strength,agility,energy=need('require_strength'),need('require_agility'),need('require_energy')
    total=20+5*(LEVEL-1);vitality=total-strength-agility-energy
    assert vitality>=need('require_tili')
    prop=bytearray(bytes.fromhex(value(status,'property')))
    old=struct.unpack_from('<6i',prop)
    assert old[:4]==(5,5,5,5) and value(status,'pp')=='0'
    cfg=next(c for c in server['CHARRACTER_CLASS_CONFIG'].values() if c['character_class_id']==cls)
    # player_template::LevelUp per level from 1 to 99, UpdateBasic for the spent points.
    grow=lambda k:int(LEVEL*k)-int(k)
    max_hp=old[4]+(LEVEL-1)*cfg['lvlup_hp']+(vitality-5)*cfg['vit_hp']
    max_mp=old[5]+(LEVEL-1)*cfg['lvlup_mp']+(energy-5)*cfg['eng_mp']
    struct.pack_into('<6i',prop,0,vitality,energy,strength,agility,max_hp,max_mp)
    for offset,k in ((0x34,cfg['lvlup_dmg']),(0x6c,cfg['lvlup_magic'])):
        low,high=struct.unpack_from('<2i',prop,offset)
        struct.pack_into('<2i',prop,offset,low+grow(k),high+grow(k))
    for name,v in (('level',LEVEL),('exp',0),('pp',0),('hp',max_hp),('mp',max_mp),('property',prop.hex())):
        variable(status,name).text=str(v)
    # Skills: id, ability, level. Existing entries (town portal) are kept.
    blob=bytes.fromhex(value(status,'skills'))
    existing=[struct.unpack_from('<3i',blob,4+12*i) for i in range(struct.unpack_from('<i',blob)[0])]
    learned=class_skills(extra,cls);ids={s for s,_ in learned}
    entries=[e for e in existing if e[0] not in ids]+[(s,0,l) for s,l in learned]
    variable(status,'skills').text=(struct.pack('<i',len(entries))+b''.join(struct.pack('<3i',*e) for e in entries)).hex()
    eq=root.find('equipment');pocket=root.find('pocket')
    for old_item in list(eq.findall('inv')):
        if int(value(old_item,'pos')) in dict((p,0) for p,*_ in records):eq.remove(old_item)
    report=[]
    for pos,item_id,kind,r in records:
        data,holes=equipment_data(r,kind,server)
        item(eq,{'id':item_id,'pos':pos,'count':1,'max_count':r['pile_num_max'],'data':data,'proctype':r['proc_type'],
                 'expire_date':0,'guid1':0,'guid2':0,'mask':1<<pos},'inv')
        report.append({'slot':pos,'id':item_id,'name':r['Name'],'refine':REFINE,'sockets':holes})
    occupied={int(value(i,'pos')) for i in pocket.findall('items')}
    for kind,item_id,mask,total_key in (('AUTOHP_ESSENCE',HP_CHARM,1<<20,'total_hp'),('AUTOMP_ESSENCE',MP_CHARM,1<<21,'total_mp')):
        r=server[kind][item_id];pos=next(i for i in range(int(value(pocket,'capacity'))) if i not in occupied);occupied.add(pos)
        item(pocket,{'id':item_id,'pos':pos,'count':1,'max_count':r['pile_num_max'],
                     'data':struct.pack('<if',r[total_key],r['trigger_amount']).hex(),'proctype':r['proc_type'],
                     'expire_date':0,'guid1':0,'guid2':0,'mask':mask},'items')
        report.append({'slot':f'inventory {pos}','id':item_id,'name':r['Name']})
    ET.indent(root)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True),{
        'role':rid,'class':CLASS_NAMES[cls],'gender':int(value(base,'gender')),'level':LEVEL,
        'stats':{'vitality':vitality,'magic':energy,'strength':strength,'dexterity':agility},
        'max_hp':max_hp,'max_mp':max_mp,'skills':len(learned),'items':report}

def role_xml(out):
    start=out.find(b'<?xml');end=out.rfind(b'</role>')
    if start<0 or end<0:raise RuntimeError('Native role export returned no XML: '+out[-300:].decode(errors='replace'))
    return out[start:end+7]

def canonical(node):
    # Native export normalizes field ordering; every value still participates.
    return (node.tag,tuple(sorted(node.attrib.items())),(node.text or '').strip(),tuple(sorted(canonical(x) for x in node)))

def run(volumes,image,directory,script):
    """Run a shell script offline against the gamedbd /home volume(s)."""
    return command(['docker','run','--rm','--network','none',*volumes,
                    '--mount',f'type=bind,source={directory},target=/edit',
                    '--workdir','/home','--entrypoint','sh',image,'-c',script],timeout=600)

def pipeline(volumes,image,directory):
    server,client,extra=load()
    patched=export_binary();(directory/'gamedbd-export').write_bytes(patched.read_bytes())
    exporter='cp /edit/gamedbd-export /tmp/gx && chmod +x /tmp/gx && '
    reports=[];edited_ids=[]
    try:
        for rid in TEMPLATES:
            xml=role_xml(run(volumes,image,directory,exporter+f'/tmp/gx gamesys.conf exportrole {rid}'))
            (directory/f'before-{rid}.xml').write_bytes(xml)
            root=ET.fromstring(xml)
            if not value(root.find('status'),'skills'):continue  # empty gender-locked template
            edited,report=prepare(xml,server,client,extra)
            (directory/f'edited-{rid}.xml').write_bytes(edited);reports.append(report);edited_ids.append(rid)
    finally:
        (directory/'gamedbd-export').unlink()
    assert sorted(r['class'] for r in reports)==sorted(CLASS_NAMES),'Expected one template per class'
    (directory/'loadout.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    for rid in edited_ids:
        (directory/f'import-{rid}.log').write_bytes(run(volumes,image,directory,f'./gamedbd gamesys.conf importrole /edit/edited-{rid}.xml'))
        actual=role_xml(run(volumes,image,directory,f'./gamedbd gamesys.conf exportrole {rid}'))
        (directory/f'after-{rid}.xml').write_bytes(actual)
        expected=ET.fromstring((directory/f'edited-{rid}.xml').read_bytes());got=ET.fromstring(actual)
        for section in ['base','status','pocket','equipment','storehouse']:
            assert canonical(expected.find(section))==canonical(got.find(section)),f'Native import differs in {section} of {rid}'
    md5='md5sum clsconfig dbhomewdb/dbdata/clsconfig'
    before=run(volumes,image,directory,md5).decode()
    out=run(volumes,image,directory,'./gamedbd gamesys.conf exportclsconfig && '+md5)
    (directory/'exportclsconfig.log').write_bytes(out)
    after=[l.split()[0] for l in out.decode().splitlines() if l.endswith('clsconfig')]
    old=[l.split()[0] for l in before.splitlines() if l.endswith('clsconfig')]
    assert len(after)==2 and after!=old,'exportclsconfig changed nothing'
    # gamedbd copies ./clsconfig over the table at startup, so both must hold the export.
    if after[0]!=after[1]:
        changed,other=('clsconfig','dbhomewdb/dbdata/clsconfig') if after[0]!=old[0] else ('dbhomewdb/dbdata/clsconfig','clsconfig')
        run(volumes,image,directory,f'cp -f {changed} {other} && '+md5)
    final=run(volumes,image,directory,md5).decode()
    sums={l.split()[0] for l in final.splitlines() if l.endswith('clsconfig')}
    assert len(sums)==1,'clsconfig copies differ'
    (directory/'clsconfig.md5').write_text(final)
    return reports

def gamedbd_image():
    config=json.loads(command(['docker','compose','config','--format','json']))
    return config['services']['perfectworld-gamedbd']['image']

def check_binary(container):
    live=command(['docker','exec',container,'sha256sum','/home/gamedbd']).split()[0].decode()
    assert live==sha256(ROOT/'runtime/inspect/gamedbd'),'Live gamedbd differs from runtime/inspect/gamedbd'

def scratch():
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    directory=ROOT/'runtime/class-templates'/f'scratch-{stamp}';directory.mkdir(parents=True)
    container=compose('ps','-q','perfectworld-gamedbd').decode().strip();check_binary(container)
    image=gamedbd_image();volume=f'pw-class-templates-{stamp}'
    command(['docker','volume','create',volume])
    try:
        command(['docker','run','--rm','--volumes-from',container,'-v',f'{volume}:/copy','--entrypoint','sh',image,
                 '-c','cp -a /home/. /copy/'],timeout=600)
        reports=pipeline(['-v',f'{volume}:/home'],image,directory)
        print(json.dumps({'scratch':True,'output':str(directory),'templates':reports},ensure_ascii=False,indent=2))
    finally:
        command(['docker','volume','rm','-f',volume])

def apply():
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    directory=ROOT/'backups/class-templates'/stamp;directory.mkdir(parents=True)
    container=compose('ps','-q','perfectworld-gamedbd').decode().strip();check_binary(container)
    image=gamedbd_image();stopped=False
    try:
        # Disconnect first so online characters are saved through the normal logout.
        compose('stop','-t','20','perfectworld-glinkd');time.sleep(6)
        compose('stop','-t','30','perfectworld-gamed');compose('stop','-t','30','perfectworld-gamedbd');stopped=True
        # Full persistent game DB and clsconfig backup.
        command(['docker','cp',f'{container}:/home/dbhomewdb',str(directory/'dbhomewdb')],timeout=600)
        command(['docker','cp',f'{container}:/home/clsconfig',str(directory/'clsconfig')])
        reports=pipeline(['--volumes-from',container],image,directory)
        print(json.dumps({'applied':True,'backup':str(directory),'templates':reports},ensure_ascii=False,indent=2))
    except Exception:
        if stopped:
            # Restore the database files exactly as backed up.
            run(['--volumes-from',container],image,directory,'rm -rf /home/dbhomewdb/dbdata /home/dbhomewdb/dblogs && '
                'cp -a /edit/dbhomewdb/dbdata /edit/dbhomewdb/dblogs /home/dbhomewdb/ && cp -f /edit/clsconfig /home/clsconfig')
            print('Failure: database and clsconfig restored from',directory)
        raise
    finally:
        compose('start','perfectworld-gamedbd');time.sleep(5)
        compose('start','perfectworld-gamed','perfectworld-glinkd')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--scratch',action='store_true')
    group.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    scratch() if args.scratch else apply()
