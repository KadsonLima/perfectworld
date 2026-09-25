"""Extract the data used by edit_class_templates.py into runtime/inspect.

Skill class, rank and maximum level come from the SkillStub constructors of the
local gs binary; trainer lists, charms and class growth come from the server
elements.data. Read-only: never modifies binaries or data files.
"""
import json
from pathlib import Path
import re
import struct

from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from capstone.x86 import X86_OP_IMM, X86_OP_MEM
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[2]
INSPECT = ROOT/'runtime/inspect'
WANTED = ('NPC_SKILL_SERVICE','CHARRACTER_CLASS_CONFIG','AUTOHP_ESSENCE','AUTOMP_ESSENCE','PROJECTILE_ESSENCE')

def element_lists(path, upto=117):
    data=Path(path).read_bytes()
    version,_=struct.unpack_from('<HH',data)
    cfg=(Path(__file__).parent/f'elements-v{version}.cfg').read_text(encoding='utf-8-sig').splitlines()
    sections=[];i=2
    while i<len(cfg):
        if not cfg[i].strip():i+=1;continue
        name,offset,fields,types=cfg[i:i+4];sections.append((name,offset,fields.split(';'),types.split(';')));i+=4
    pos=4;result={}
    for index,(name,offset,fields,types) in enumerate(sections[:upto]):
        if offset=='AUTO':
            # List 20 carries an extra trailing int after its tagged blob; list 101 does not.
            length=struct.unpack_from('<I',data,pos+4)[0];pos+=(12 if index==20 else 8)+length
        else:pos+=int(offset)
        count=struct.unpack_from('<I',data,pos)[0];pos+=4
        if count>200000:raise ValueError(f'Invalid count {count} in {name}')
        short=name.split(' - ')[1]
        if short=='TALK_PROC':
            # Variable length dialogs: id, text[64], windows{id,parent,text,options{id,text[64],param}}.
            for _ in range(count):
                pos+=132;windows=struct.unpack_from('<i',data,pos)[0];pos+=4
                for _ in range(windows):
                    pos+=8;length=struct.unpack_from('<i',data,pos)[0];pos+=4+2*length
                    options=struct.unpack_from('<i',data,pos)[0];pos+=4+options*136
            continue
        sizes=[int(t.split(':')[1]) if ':' in t else {'int32':4,'float':4,'int16':2,'int64':8}[t] for t in types]
        records=[]
        for _ in range(count):
            record={}
            for field,t,size in zip(fields,types,sizes):
                value=data[pos:pos+size];pos+=size
                if t.startswith('wstring:'):v=value.decode('utf-16le',errors='replace').split('\0')[0]
                elif t.startswith('string:'):v=value.split(b'\0')[0].decode('gb18030',errors='replace')
                else:v=struct.unpack('<'+{'int32':'i','int16':'h','int64':'q','float':'f'}[t],value)[0]
                record[field]=v
            records.append(record)
        if short in WANTED:result[short]=records
    return result

def skill_stubs(path):
    """cls (+0x08), max_level (+0x18) and rank (+0x1e) set by each SkillNStub constructor."""
    symbols=json.loads((INSPECT/'gs-symbols.json').read_text())
    f=open(path,'rb');elf=ELFFile(f)
    segments=[(s['p_vaddr'],s['p_offset'],s['p_filesz']) for s in elf.iter_segments() if s['p_type']=='PT_LOAD']
    def read(address,size):
        for vaddr,offset,filesz in segments:
            if 0<=address-vaddr<filesz:f.seek(offset+address-vaddr);return f.read(size)
    md=Cs(CS_ARCH_X86,CS_MODE_32);md.detail=True
    vectors={a for n,(a,_) in symbols.items() if n.startswith('_ZNSt6vector')}
    result={}
    for name,(address,size) in symbols.items():
        m=re.fullmatch(r'_ZN4GNET\d+Skill(\d+)StubC1Ev',name)
        if not m:continue
        fields={};strings={};pushed=None
        for i in md.disasm(read(address,min(size,700)),address):
            if i.mnemonic=='push' and i.operands[0].type==X86_OP_IMM:pushed=i.operands[0].imm
            if i.mnemonic=='add' and i.op_str in ('eax, 0xc','eax, 0x10'):strings[i.op_str]=pushed
            if (i.mnemonic=='mov' and len(i.operands)==2 and i.operands[0].type==X86_OP_MEM
                    and i.operands[1].type==X86_OP_IMM and i.reg_name(i.operands[0].mem.base)=='eax'):
                fields.setdefault(i.operands[0].mem.disp,i.operands[1].imm)
            # Scalar fields are all assigned before the first vector push_back.
            if i.mnemonic=='call' and i.operands[0].type==X86_OP_IMM and i.operands[0].imm in vectors:break
        native=read(strings['eax, 0x10'],120).split(b'\0')[0].decode('gb18030','replace') if 'eax, 0x10' in strings else ''
        result[int(m.group(1))]={'cls':fields.get(8),'max_level':fields.get(0x18),'rank':fields.get(0x1e),'native':native}
    return result

if __name__=='__main__':
    lists=element_lists(INSPECT/'server-elements.data')
    client=element_lists(Path(r'D:\Perfect World International 155 v159\element\data\elements.data'))
    for kind in ('AUTOHP_ESSENCE','AUTOMP_ESSENCE'):
        # The client must know the same charms, otherwise they appear as unknown items.
        known={r['ID'] for r in client[kind]}
        lists[kind]=[r for r in lists[kind] if r['ID'] in known]
    lists['SKILLS']=skill_stubs(INSPECT/'gs')
    out=INSPECT/'class-template-data.json'
    out.write_text(json.dumps(lists,ensure_ascii=False),encoding='utf-8')
    print({k:len(v) for k,v in lists.items()})
