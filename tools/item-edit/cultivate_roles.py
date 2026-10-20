"""Give existing characters (roles >= 1024) cultivation 89 and 2 chi sparks.

Only raises: cultivation below level2 8 becomes 8 (sage/demon values are kept)
and base maximum chi below 200 becomes 200. Nothing else in the role changes.
Stops glinkd/gamed/gamedbd, backs up /home/dbhomewdb, imports offline with the
native role XML tools and compares every section after import.

  python cultivate_roles.py           shows what would change
  python cultivate_roles.py --apply   applies
"""
import argparse
import csv
from datetime import datetime
import io
import json
import struct
import time
import xml.etree.ElementTree as ET

from edit_nirvana import ROOT, command, compose, variable, value
from edit_class_templates import CULTIVATION, MAX_CHI, MAX_CHI_OFFSET, canonical, gamedbd_image, role_xml, run

def roles(volumes,image,directory):
    out=run(volumes,image,directory,'./gamedbd gamesys.conf listrolebrief').decode('utf-8','replace')
    lines=out.splitlines();start=next(i for i,l in enumerate(lines) if l.startswith('roleid,'))
    return [r for r in csv.DictReader(io.StringIO('\n'.join(lines[start:]))) if r['roleid'].isdigit() and int(r['roleid'])>=1024]

def raise_cultivation(xml):
    root=ET.fromstring(xml);status=root.find('status')
    prop=bytearray(bytes.fromhex(value(status,'property')))
    level2=int(value(status,'level2'));chi=struct.unpack_from('<i',prop,MAX_CHI_OFFSET)[0]
    changes={}
    if level2<CULTIVATION:
        variable(status,'level2').text=str(CULTIVATION);changes['cultivation']=[level2,CULTIVATION]
    if chi<MAX_CHI:
        struct.pack_into('<i',prop,MAX_CHI_OFFSET,MAX_CHI);variable(status,'property').text=prop.hex()
        changes['max_chi']=[chi,MAX_CHI]
    ET.indent(root)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True),changes

def process(volumes,image,directory,apply):
    report=[]
    for row in roles(volumes,image,directory):
        rid=int(row['roleid'])
        xml=role_xml(run(volumes,image,directory,f'./gamedbd gamesys.conf exportrole {rid}'))
        (directory/f'before-{rid}.xml').write_bytes(xml)
        edited,changes=raise_cultivation(xml)
        report.append({'role':rid,'name':row['name'].strip('"'),'changes':changes or 'nenhuma'})
        if not changes or not apply:continue
        (directory/f'edited-{rid}.xml').write_bytes(edited)
        (directory/f'import-{rid}.log').write_bytes(run(volumes,image,directory,f'./gamedbd gamesys.conf importrole /edit/edited-{rid}.xml'))
        actual=role_xml(run(volumes,image,directory,f'./gamedbd gamesys.conf exportrole {rid}'))
        (directory/f'after-{rid}.xml').write_bytes(actual)
        expected=ET.fromstring(edited);got=ET.fromstring(actual)
        for section in ['base','status','pocket','equipment','storehouse','task']:
            if expected.find(section) is None:continue
            assert canonical(expected.find(section))==canonical(got.find(section)),f'Native import differs in {section} of {rid}'
    return report

def main(apply):
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    directory=ROOT/('backups' if apply else 'runtime')/'cultivation'/stamp;directory.mkdir(parents=True)
    container=compose('ps','-q','perfectworld-gamedbd').decode().strip();image=gamedbd_image()
    volumes=['--volumes-from',container]
    if not apply:
        # Read-only preview on a copy so the running database is never opened twice.
        volume=f'pw-cultivation-{stamp}';command(['docker','volume','create',volume])
        try:
            command(['docker','run','--rm','--volumes-from',container,'-v',f'{volume}:/copy','--entrypoint','sh',image,
                     '-c','cp -a /home/. /copy/'],timeout=600)
            print(json.dumps(process(['-v',f'{volume}:/home'],image,directory,False),ensure_ascii=False,indent=2))
        finally:command(['docker','volume','rm','-f',volume])
        return
    stopped=False
    try:
        # Disconnect first so online characters are saved through the normal logout.
        compose('stop','-t','20','perfectworld-glinkd');time.sleep(6)
        compose('stop','-t','30','perfectworld-gamed');compose('stop','-t','30','perfectworld-gamedbd');stopped=True
        command(['docker','cp',f'{container}:/home/dbhomewdb',str(directory/'dbhomewdb')],timeout=600)
        report=process(volumes,image,directory,True)
        (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'applied':True,'backup':str(directory),'roles':report},ensure_ascii=False,indent=2))
    except Exception:
        if stopped:
            run(volumes,image,directory,'rm -rf /home/dbhomewdb/dbdata /home/dbhomewdb/dblogs && '
                'cp -a /edit/dbhomewdb/dbdata /edit/dbhomewdb/dblogs /home/dbhomewdb/')
            print('Failure: database restored from',directory)
        raise
    finally:
        compose('start','perfectworld-gamedbd');time.sleep(5)
        compose('start','perfectworld-gamed','perfectworld-glinkd')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    main(parser.parse_args().apply)
