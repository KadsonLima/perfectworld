"""Offline edit of existing characters (roles >= 1024) with the native role XML
tools: stops glinkd/gamed/gamedbd, backs up /home/dbhomewdb, imports each
edited role and compares every section after import. Without apply it only
reports, on a throwaway copy of the database.

transform(root, row) edits the parsed role in place and returns its changes
(falsy when the role is left alone).
"""
from datetime import datetime
import json
import time
import xml.etree.ElementTree as ET

from edit_nirvana import ROOT, command, compose
from edit_class_templates import canonical, gamedbd_image, role_xml, run
from cultivate_roles import roles

def process(volumes,image,directory,transform,apply):
    report=[]
    for row in roles(volumes,image,directory):
        rid=int(row['roleid'])
        xml=role_xml(run(volumes,image,directory,f'./gamedbd gamesys.conf exportrole {rid}'))
        root=ET.fromstring(xml)
        changes=transform(root,row)
        if not changes:continue
        (directory/f'before-{rid}.xml').write_bytes(xml)
        report.append({'role':rid,'name':row['name'].strip('"'),'changes':changes})
        if not apply:continue
        ET.indent(root);edited=ET.tostring(root,encoding='utf-8',xml_declaration=True)
        (directory/f'edited-{rid}.xml').write_bytes(edited)
        (directory/f'import-{rid}.log').write_bytes(run(volumes,image,directory,f'./gamedbd gamesys.conf importrole /edit/edited-{rid}.xml'))
        actual=role_xml(run(volumes,image,directory,f'./gamedbd gamesys.conf exportrole {rid}'))
        (directory/f'after-{rid}.xml').write_bytes(actual)
        got=ET.fromstring(actual)
        for section in ['base','status','pocket','equipment','storehouse','task']:
            if root.find(section) is None:continue
            assert canonical(root.find(section))==canonical(got.find(section)),f'Native import differs in {section} of {rid}'
    return report

def edit_roles(transform,name,apply):
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    directory=ROOT/('backups' if apply else 'runtime')/name/stamp;directory.mkdir(parents=True)
    container=compose('ps','-q','perfectworld-gamedbd').decode().strip();image=gamedbd_image()
    volumes=['--volumes-from',container]
    if not apply:
        # Read-only preview on a copy so the running database is never opened twice.
        volume=f'pw-{name}-{stamp}';command(['docker','volume','create',volume])
        try:
            command(['docker','run','--rm','--volumes-from',container,'-v',f'{volume}:/copy','--entrypoint','sh',image,
                     '-c','cp -a /home/. /copy/'],timeout=600)
            print(json.dumps(process(['-v',f'{volume}:/home'],image,directory,transform,False),ensure_ascii=False,indent=2))
        finally:command(['docker','volume','rm','-f',volume])
        return
    stopped=False
    try:
        # Disconnect first so online characters are saved through the normal logout.
        compose('stop','-t','20','perfectworld-glinkd');time.sleep(6)
        compose('stop','-t','30','perfectworld-gamed');compose('stop','-t','30','perfectworld-gamedbd');stopped=True
        command(['docker','cp',f'{container}:/home/dbhomewdb',str(directory/'dbhomewdb')],timeout=600)
        report=process(volumes,image,directory,transform,True)
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
