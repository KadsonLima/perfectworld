"""Prepare/apply the local KakA test loadout using the native role XML tools.

Defaults to preparation only. --apply disconnects players briefly, saves a full
game database backup, imports offline and verifies the result before restarting.
"""
import argparse
import copy
from datetime import datetime
import json
from pathlib import Path
import struct
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
ROLE = 1024
PLAN = [(0,34778,'WEAPON_ESSENCE'), (1,33308,'ARMOR_ESSENCE'),
        (2,23614,'DECORATION_ESSENCE'), (3,34758,'ARMOR_ESSENCE'),
        (4,32525,'ARMOR_ESSENCE'), (5,24686,'DECORATION_ESSENCE'),
        (6,32519,'ARMOR_ESSENCE'), (7,32531,'ARMOR_ESSENCE'),
        (8,32513,'ARMOR_ESSENCE'), (9,26388,'DECORATION_ESSENCE'),
        (10,26388,'DECORATION_ESSENCE')]

def command(args, timeout=120):
    p = subprocess.run(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    if p.returncode:
        raise RuntimeError(p.stderr.decode('utf-8',errors='replace') + p.stdout.decode('utf-8',errors='replace'))
    return p.stdout

def compose(*args):
    return command(['docker','compose',*args])

def variable(node,name):
    v = node.find(f"variable[@name='{name}']")
    if v is None:raise ValueError(f'Missing {name}')
    return v

def value(node,name):return variable(node,name).text or ''

def addon(aid,*params,stone=False):
    assert 1 <= len(params) <= 3
    return struct.pack('<I'+'i'*len(params),aid | (len(params)<<13) | (0x8000 if stone else 0),*params)

def catalog():
    server=json.loads((ROOT/'runtime/inspect/server-items.json').read_text(encoding='utf-8'))
    client=json.loads((ROOT/'runtime/inspect/client-items.json').read_text(encoding='utf-8'))
    return ({k:{r['ID']:r for r in v} for k,v in server.items()},
            {k:{r['ID']:r for r in v} for k,v in client.items()})

def equipment_data(r,kind,pos,server):
    dur=r['durability_max']*100
    header=struct.pack('<6H2I',r['require_level'],r['character_combo_id'],
                       r['require_strength'],r['require_tili'],r['require_agility'],r['require_energy'],dur,dur)
    sockets=[]
    if kind=='WEAPON_ESSENCE':
        sub=server['WEAPON_SUB_TYPE'][r['id_sub_type']]
        ticks=round(sub['attack_speed']*20)
        essence=struct.pack('<9i2f',0,r['id_major_type'],r['level'],r['require_projectile'],
                            r['damage_low'],r['damage_high_max'],r['magic_damage_low'],r['magic_damage_high_max'],
                            ticks,r['attack_range'],sub['attack_short_range'])
        # Native generation converts interval seconds to 20 Hz ticks.
        bonuses=[addon(2037,40),addon(337,2),addon(1479,19),addon(474,2)]
        sockets=[2000]*2
    elif kind=='ARMOR_ESSENCE':
        essence=struct.pack('<9i',r['defence_high'],r['armor_enhance_high'],r['mp_enhance_high'],
                            r['hp_enhance_high'],*[r[f'magic_defences_{i}_high'] for i in range(1,6)])
        bonuses=[addon(2745,12),addon(2746,12),addon(2747,12)]
        if pos in (3,8):bonuses[-1]=addon(337,2)
        sockets=[38155]*4
    else:
        essence=struct.pack('<9i',r['damage_high'],r['magic_damage_high'],r['defence_high'],
                            r['armor_enhance_high'],*[r[f'magic_defences_{i}_high'] for i in range(1,6)])
        bonuses=[addon(1453,12),addon(1458,12),addon(1468,12)]
        if pos in (9,10):bonuses.append(addon(585,4))
    aid=r['levelup_addon']
    bonuses.append(addon(aid,int(server['EQUIPMENT_ADDON'][aid]['param1']*37.5),12))
    for stone_id in sockets:
        stone=server['STONE_ESSENCE'][stone_id]
        aid=stone['id_addon_damage' if kind=='WEAPON_ESSENCE' else 'id_addon_defence']
        bonuses.append(addon(aid,server['EQUIPMENT_ADDON'][aid]['param1'],stone=True))
    return (header+struct.pack('<HBB',len(essence),3,0)+essence+struct.pack('<I',len(sockets))+
            b''.join(struct.pack('<I',sid) for sid in sockets)+struct.pack('<I',len(bonuses))+
            b''.join(bonuses)).hex()

def validate_data(data,kind):
    b=bytes.fromhex(data)
    size=struct.unpack_from('<H',b,20)[0]
    assert size==(44 if kind=='WEAPON_ESSENCE' else 36)
    offset=24+b[23]+size
    count=struct.unpack_from('<I',b,offset)[0];offset+=4
    assert count in (0,2,4)
    offset+=count*4
    count=struct.unpack_from('<I',b,offset)[0];offset+=4
    refine=[]
    for _ in range(count):
        aid=struct.unpack_from('<I',b,offset)[0];offset+=4
        n=(aid>>13)&3
        assert n in (1,2,3)
        params=struct.unpack_from('<'+'i'*n,b,offset);offset+=n*4
        if n==2:refine.append(params)
    assert offset==len(b) and len(refine)==1 and refine[0][1]==12

def prepare(xml):
    server,client=catalog()
    root=ET.fromstring(xml)
    assert value(root.find('base'),'id')==str(ROLE)
    assert value(root.find('base'),'name')=='KakA'
    assert value(root.find('base'),'cls')=='0'
    assert int(value(root.find('status'),'level'))>=100
    pocket=root.find('pocket');eq=root.find('equipment');status=root.find('status')
    variable(pocket,'capacity').text='64'
    # Spend existing stat points; leave the remaining serialized property intact.
    prop=bytes.fromhex(value(status,'property'))
    old=struct.unpack_from('<4i',prop)
    total=sum(old)+int(value(status,'pp'))
    stats=(total-252-188-5,5,252,188)  # vitality, magic, strength, dexterity
    assert stats[0]>=5
    variable(status,'property').text=(struct.pack('<4i',*stats)+prop[16:]).hex()
    variable(status,'pp').text='0'
    occupied={int(value(i,'pos')) for i in pocket.findall('items')}
    report=[]
    for pos,item_id,kind in PLAN:
        r=server[kind][item_id];c=client[kind][item_id]
        # Essential numeric equipment definitions must agree in both versions.
        for key,v in r.items():
            if key in c and isinstance(v,(int,float)):
                assert v==c[key],f'Catalog mismatch {item_id}: {key}'
        assert stats[2]>=r['require_strength'] and stats[3]>=r['require_agility']
        for old_item in list(eq.findall('inv')):
            if int(value(old_item,'pos'))==pos:
                free=next(i for i in range(64) if i not in occupied)
                saved=copy.deepcopy(old_item);saved.tag='items'
                variable(saved,'pos').text=str(free)
                # Keep native XML ordering: items precede reserved variables.
                reserved=pocket.find("variable[@name='reserved1']")
                if reserved is None:pocket.append(saved)
                else:pocket.insert(list(pocket).index(reserved),saved)
                occupied.add(free);eq.remove(old_item)
        data=equipment_data(r,kind,pos,server);validate_data(data,kind)
        item=ET.SubElement(eq,'inv')
        # Ring equip masks allow both native ring positions.
        mask=1536 if pos in (9,10) else 1<<pos
        fields={'id':item_id,'pos':pos,'count':1,'max_count':r['pile_num_max'],'data':data,
                'proctype':r['proc_type'],'expire_date':0,'guid1':0,'guid2':0,'mask':mask}
        for name,v in fields.items():
            ET.SubElement(item,'variable',name=name,type='Octets' if name=='data' else 'int').text=str(v)
        report.append({'slot':pos,'id':item_id,'name':r['Name'],'refine':12,'sockets':2 if pos==0 else (4 if kind=='ARMOR_ESSENCE' else 0)})
    ET.indent(root)
    edited=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    return edited,{'role':ROLE,'name':'KakA','inventory':64,'stats':stats,'equipment':report,'weapon_interval_seconds':-0.10}

def export_live():
    out=compose('exec','-T','-w','/home','perfectworld-gamedbd','./gamedbd','gamesys.conf','exportrole',str(ROLE))
    start=out.find(b'<?xml');end=out.rfind(b'</role>')
    if start<0 or end<0:raise RuntimeError('Native role export returned no XML')
    return out[start:end+7]

def apply():
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    directory=ROOT/'backups/characters'/f'KakA-{ROLE}-nirvana-{stamp}'
    directory.mkdir(parents=True)
    config=json.loads((ROOT/'docker-compose.yaml').read_text())
    image=config['services']['perfectworld-gamedbd']['image']
    container=compose('ps','-q','perfectworld-gamedbd').decode().strip()
    def offline(*args):
        return command(['docker','run','--rm','--network','none','--volumes-from',container,
                        '--mount',f'type=bind,source={directory},target=/edit','--workdir','/home',
                        '--entrypoint','/home/gamedbd',image,'gamesys.conf',*args])
    imported=False
    try:
        # Disconnect first so the online character is saved through normal logout.
        compose('stop','-t','20','perfectworld-glinkd')
        time.sleep(6)
        original=export_live()
        (directory/'before.xml').write_bytes(original)
        edited,report=prepare(original)
        (directory/'edited.xml').write_bytes(edited)
        (directory/'loadout.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        compose('stop','-t','30','perfectworld-gamed')
        compose('stop','-t','30','perfectworld-gamedbd')
        # Full persistent game DB backup in addition to the individual role XML.
        command(['docker','cp',f'{container}:/home/dbhomewdb',str(directory/'dbhomewdb')])
        imported=True
        out=offline('importrole','/edit/edited.xml')
        (directory/'import.log').write_bytes(out)
        out=offline('exportrole',str(ROLE))
        start=out.find(b'<?xml');end=out.rfind(b'</role>')
        actual=out[start:end+7]
        (directory/'after.xml').write_bytes(actual)
        expected=ET.fromstring(edited);got=ET.fromstring(actual)
        for section in ['base','status','pocket','equipment','storehouse','task']:
            a=expected.find(section);b=got.find(section)
            if a is None:continue
            def canonical(node):
                # Native export normalizes field ordering; inventory positions
                # and every field value still participate in the comparison.
                return (node.tag,tuple(sorted(node.attrib.items())),(node.text or '').strip(),tuple(sorted(canonical(x) for x in node)))
            assert canonical(a)==canonical(b),f'Native import differs in {section}'
        print(json.dumps({'applied':True,'backup':str(directory),**report},ensure_ascii=True,indent=2))
    except Exception:
        if imported:
            (directory/'rollback.log').write_bytes(offline('importrole','/edit/before.xml'))
        raise
    finally:
        compose('start','perfectworld-gamedbd')
        time.sleep(3)
        compose('start','perfectworld-gamed','perfectworld-glinkd')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if args.apply:apply()
    else:
        xml=export_live();edited,report=prepare(xml)
        (ROOT/'runtime/inspect/KakA-nirvana-preview.xml').write_bytes(edited)
        print(json.dumps(report,ensure_ascii=True,indent=2))
