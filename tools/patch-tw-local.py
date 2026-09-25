"""Prepare narrowly scoped local TW patches for the pinned 1.5.5 binaries.

Original binaries must be in runtime/inspect (docker compose cp). This script
does not restart services. Compose mounts runtime/patches over the originals.
"""
import hashlib
import json
from pathlib import Path
import struct
import argparse
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--output',default='runtime/patches')
args=parser.parse_args()
OUT=ROOT/args.output
OUT.mkdir(parents=True,exist_ok=True)
EXPECTED={'gfactiond':'88651c8a384f630edbbed80ebddbedd7717071a32baad5610a39614dd86ce8c1',
          'gdeliveryd':'fa69f5fb99759a6ca3c4d18b109b56a757e0dfaa951d4bfa7ae1e37a7042effe'}
BACKUP=ROOT/'backups/tw-binaries-original'
BACKUP.mkdir(parents=True,exist_ok=True)

def digest(b):return hashlib.sha256(b).hexdigest()

def save_binary(name,data):
    # Never truncate an executable that a running container may have mapped.
    temporary=OUT/(name+'.next')
    temporary.write_bytes(data)
    temporary.replace(OUT/name)

def original(name):
    p=ROOT/'runtime/inspect'/name
    data=p.read_bytes()
    assert digest(data)==EXPECTED[name],f'Unexpected original binary: {name}'
    backup=BACKUP/name
    if backup.exists():assert digest(backup.read_bytes())==EXPECTED[name]
    else:backup.write_bytes(data)
    return bytearray(data),ELFFile(p.open('rb'))

def offset(elf,address):
    for segment in elf.iter_segments():
        if segment['p_type']=='PT_LOAD' and segment['p_vaddr']<=address<segment['p_vaddr']+segment['p_filesz']:
            return segment['p_offset']+address-segment['p_vaddr']
    raise ValueError('Address outside file-backed load segments')

manifest={'minimum_clan_seconds':60,'battle_duration_seconds':86400,'patches':{}}
data,elf=original('gfactiond')
position=offset(elf,0x80e4a20)
assert data[position:position+6]==bytes.fromhex('81fa3f7e0500')
assert data[position+6:position+12]==bytes.fromhex('0f8f78010000')
data[position+2:position+6]=struct.pack('<I',59)
assert data[position:position+6]==bytes.fromhex('81fa3b000000')
save_binary('gfactiond',data)
manifest['patches']['gfactiond']={'original_sha256':EXPECTED['gfactiond'],'patched_sha256':digest(data),
    'address':'0x80e4a20','change':'elapsed clan membership >= 360000 seconds becomes >= 60 seconds'}

data,elf=original('gdeliveryd')
hook=0x8344413
position=offset(elf,hook)
replaced=bytes.fromhex('8b4510894210')
assert data[position:position+6]==replaced
segment=elf.get_segment(2)
next_segment=elf.get_segment(3)
assert segment['p_type']=='PT_LOAD' and segment['p_flags']==5
cave_offset=segment['p_offset']+segment['p_filesz']
cave_address=segment['p_vaddr']+segment['p_filesz']
assert cave_offset==0x61bec0 and cave_address==0x8663ec0
gap=next_segment['p_offset']-cave_offset
assert gap==320 and data[cave_offset:cave_offset+gap]==bytes(gap)

# TestBattle sets the challenger but omits the phase, battle timestamp and
# faction synchronization used by the client's territory map and TW NPC.
# Execute the replaced stores, preserve flags/registers, fill the timestamp
# from TestBattle's existing current-time local and use native notifications.
code=bytearray(replaced+bytes.fromhex('9c608b45ec89421c8b5d08836318fe834b180a'))
# Account for the trampoline return address, flags and saved registers so
# nested native calls preserve the original 16-byte stack alignment.
code.extend(bytes.fromhex('83ec08'))
def call(address):
    here=cave_address+len(code)
    code.extend(b'\xe8'+struct.pack('<i',address-here-5))
for address in [0x833dd5c,0x833dbea]:
    code.extend(bytes.fromhex('83ec0c53'))
    call(address)
    code.extend(bytes.fromhex('83c410'))
# A native log verifies this hook actually ran after the fields were populated.
fmt=b'PW local TW: map synced, membership minimum=60 seconds\0'
fmt_address=cave_address+len(code)+22
code.extend(bytes.fromhex('83ec0c')+b'\x68'+struct.pack('<I',fmt_address))
call(0x8050e7c)
code.extend(bytes.fromhex('83c41083c408619dc3'))
assert cave_address+len(code)==fmt_address
instructions=list(Cs(CS_ARCH_X86,CS_MODE_32).disasm(bytes(code),cave_address))
assert sum(i.size for i in instructions)==len(code)
assert [i.mnemonic for i in instructions].count('call')==3
payload=code+fmt

# Schedule every battle selected by the native allocator at real time + 300s.
# Timer::GetTime is a single load from 0x868fca4 in this exact ELF. Preserve
# flags: the replaced instruction is MOV, and only EAX is an output.
schedule_address=cave_address+len(payload)
assert data[offset(elf,0x80afd08):offset(elf,0x80afd08)+10]==bytes.fromhex('5589e5a1a4fc6808c9c3')
schedule_code=bytes.fromhex('9ca1a4fc6808052c0100009dc3')
payload+=schedule_code
schedule_hook=0x8343e1b
schedule_pos=offset(elf,schedule_hook)
assert data[schedule_pos:schedule_pos+6]==bytes.fromhex('8b858cfeffff')
data[schedule_pos:schedule_pos+6]=b'\xe8'+struct.pack('<i',schedule_address-schedule_hook-5)+b'\x90'
# The original weekly rollover would push a Monday/Tuesday manual round into
# next week. Our absolute real timestamp must not pass through that adjustment.
rollover=offset(elf,0x8343e58)
assert data[rollover:rollover+2]==bytes.fromhex('7d22')
data[rollover]=0xeb

# Bidding keeps its simulated clock; UpdateBattle receives real wall time.
# At the original call site: [ESP+4]=this, [ESP+8]=timestamp on entry.
update_address=cave_address+len(payload)
update_code=bytearray(bytes.fromhex('a1a4fc680889442408'))
update_code+=b'\xe9'+struct.pack('<i',0x8341e82-(update_address+len(update_code))-5)
payload+=update_code
update_hook=0x83424ab
update_pos=offset(elf,update_hook)
assert data[update_pos:update_pos+5]==b'\xe8'+struct.pack('<i',0x8341e82-update_hook-5)
data[update_pos:update_pos+5]=b'\xe8'+struct.pack('<i',update_address-update_hook-5)
# Completion timestamps and OnBattleStart's timeout also need real time.
for address in (0x8342612,0x8342ae0,0x8342c00):
    pos=offset(elf,address)
    assert data[pos:pos+5]==b'\xe8'+struct.pack('<i',0x83408c0-address-5)
    data[pos:pos+5]=b'\xe8'+struct.pack('<i',0x80afd08-address-5)
# Start when now == battle_time too, not one additional 60s tick later.
start_compare=offset(elf,0x83422b4)
assert data[start_compare:start_compare+2]==bytes.fromhex('0f8d')
data[start_compare+1]=0x8f
# TestBattle's native duration is 1800 seconds. Extend it to 24 hours.
duration_pos=offset(elf,0x834441c)
assert data[duration_pos:duration_pos+5]==bytes.fromhex('0508070000')
data[duration_pos+1:duration_pos+5]=struct.pack('<I',86400)
assert len(payload)<=gap
data[cave_offset:cave_offset+len(payload)]=payload
data[position:position+6]=b'\xe8'+struct.pack('<i',cave_address-hook-5)+b'\x90'
# Extend the RX segment only into its verified empty file gap; no sections or
# writable mappings are moved. ELF32 p_filesz/p_memsz are offsets 16 and 20.
ph=elf.header['e_phoff']+2*elf.header['e_phentsize']
size=segment['p_filesz']+len(payload)
struct.pack_into('<II',data,ph+16,size,size)
save_binary('gdeliveryd',data)
manifest['patches']['gdeliveryd']={'original_sha256':EXPECTED['gdeliveryd'],'patched_sha256':digest(data),
    'address':hex(hook),'trampoline':hex(cave_address),'payload_bytes':len(payload),
    'change':'TestBattle map synchronization and 24h duration; native rounds scheduled 300s after closing; battles use real time',
    'battle_delay_seconds':300,'schedule_hook':hex(schedule_hook),'schedule_trampoline':hex(schedule_address),
    'battle_duration_seconds':86400,'duration_patch_address':'0x834441c',
    'update_trampoline':hex(update_address),'real_time_calls':['0x8342612','0x8342ae0','0x8342c00'],
    'instructions':[f'{hex(i.address)} {i.mnemonic} {i.op_str}' for i in instructions]}
(OUT/'tw-patches.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(manifest,indent=2))
