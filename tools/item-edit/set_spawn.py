"""Birth position of new characters: the posx/posy/posz/worldtag of the class
templates (roles 16-31) copied by gamedbd at creation. Only those four fields
change; the loadout set by edit_class_templates.py is kept.

Default spot: resurrection point of City of the Lost (Cidade das Feras) in the
main world gs01, from element/maps/world/precinct.clt of the client.

  --scratch  runs the whole pipeline on a throwaway copy of the gamedbd volume
  --apply    stops the game services, backs up the database and applies
"""
import argparse
import struct
import xml.etree.ElementTree as ET

from edit_nirvana import variable, value
from edit_class_templates import CLASS_NAMES, apply, scratch

WORLDTAG = 1  # gs01
POSITION = (-1551.160034, 261.372009, 978.177979)

def place(status):
    """Set the position; returns the previous one."""
    old={k:value(status,k) for k in ('posx','posy','posz','worldtag')}
    # Native export prints floats as float32 with 9 significant digits.
    for k,v in zip(('posx','posy','posz'),POSITION):
        variable(status,k).text=f"{struct.unpack('<f',struct.pack('<f',v))[0]:.9g}"
    variable(status,'worldtag').text=str(WORLDTAG)
    return old

def relocate(xml):
    root=ET.fromstring(xml);base=root.find('base')
    old=place(root.find('status'))
    ET.indent(root)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True),{
        'role':int(value(base,'id')),'class':CLASS_NAMES[int(value(base,'cls'))],'before':old}

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--scratch',action='store_true')
    group.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    (scratch if args.scratch else apply)(relocate,'spawn','spawn.json')
