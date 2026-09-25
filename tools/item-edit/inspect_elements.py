"""Read the first equipment lists of a v159 elements file."""
import json
from pathlib import Path
import struct
import sys

def lists(path):
    data=Path(path).read_bytes()
    version,signature=struct.unpack_from('<HH',data)
    if version not in (156,159):
        raise ValueError(f'Unsupported version {version}')
    cfg = (Path(__file__).parent / f'elements-v{version}.cfg').read_text(encoding='utf-8-sig').splitlines()
    sections=[]
    i=2
    while i < len(cfg):
        if not cfg[i].strip():
            i+=1;continue
        name, offset, fields, types = cfg[i:i+4]
        sections.append((name,offset,fields.split(';'),types.split(';')))
        i+=4
    pos=4
    result={}
    for index,(name,offset,fields,types) in enumerate(sections[:36]):
        if offset == 'AUTO':
            if index != 20:raise ValueError('Unsupported AUTO offset')
            length=struct.unpack_from('<I',data,pos+4)[0]
            pos += 12+length
        else:
            pos += int(offset)
        count=struct.unpack_from('<I',data,pos)[0];pos+=4
        if count>100000:raise ValueError(f'Invalid count {count} in {name}')
        sizes=[int(t.split(':')[1]) if ':' in t else {'int32':4,'float':4,'int16':2,'int64':8}[t] for t in types]
        records=[]
        for n in range(count):
            record={}
            for field,t,size in zip(fields,types,sizes):
                value=data[pos:pos+size];pos+=size
                if t.startswith('wstring:'):v=value.decode('utf-16le',errors='replace').split('\0')[0]
                elif t.startswith('string:'):v=value.split(b'\0')[0].decode('gb18030',errors='replace')
                elif t=='int32':v=struct.unpack('<i',value)[0]
                elif t=='int16':v=struct.unpack('<h',value)[0]
                elif t=='int64':v=struct.unpack('<q',value)[0]
                elif t=='float':v=struct.unpack('<f',value)[0]
                record[field]=v
            records.append(record)
        result[name.split(' - ')[1]]=records
    return result

if __name__=='__main__':
    items=lists(sys.argv[1])
    Path(sys.argv[2]).write_text(json.dumps(items,ensure_ascii=False),encoding='utf-8')
    print({name:len(values) for name,values in items.items() if name in ('EQUIPMENT_ADDON','WEAPON_ESSENCE','ARMOR_ESSENCE','STONE_ESSENCE','DECORATION_ESSENCE')})
