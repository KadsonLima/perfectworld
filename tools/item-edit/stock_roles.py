"""Give existing characters (roles >= 1024) the template supplies: inventory
money set to MONEY (the gs cap) and full stacks of the city Teleport Stones and Teleport
Incense (edit_class_templates.SUPPLIES). Supplies are only raised; nothing else changes.

  python stock_roles.py           shows what would change
  python stock_roles.py --apply   applies (stops glinkd/gamed/gamedbd, backs up)
"""
import argparse

from edit_class_templates import stock
from role_batch import edit_roles

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    edit_roles(lambda root,row:stock(root),'stock-roles',parser.parse_args().apply)
