"""Move existing characters (roles >= 1024) outside the main world gs01 to the
birth spot of set_spawn.py (Cidade das Feras). Only gs01 and the territory war
maps are started, so any other map leaves the character unable to log in.
Only posx/posy/posz/worldtag change.

  python move_roles.py           shows who would move
  python move_roles.py --apply   applies (stops glinkd/gamed/gamedbd, backs up)
"""
import argparse

from edit_nirvana import value
from role_batch import edit_roles
from set_spawn import WORLDTAG, place

def relocate(root,row):
    status=root.find('status')
    if int(value(status,'worldtag'))==WORLDTAG:return None
    return {'before':place(status)}

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    edit_roles(relocate,'move-roles',parser.parse_args().apply)
