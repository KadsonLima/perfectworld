"""Read local ELF evidence for the TW integration; never modifies binaries."""
import argparse
from pathlib import Path
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

p = argparse.ArgumentParser()
p.add_argument('binary')
p.add_argument('--match', default='BattleManager')
p.add_argument('--disassemble', action='store_true')
a = p.parse_args()
with Path(a.binary).open('rb') as f:
    elf = ELFFile(f)
    for table in (elf.get_section_by_name('.symtab'),):
        if table is None:
            print('No symbol table')
            continue
        for sym in table.iter_symbols():
            if a.match.lower() not in sym.name.lower():
                continue
            print(hex(sym['st_value']), sym['st_size'], sym.name, flush=True)
            if a.disassemble and sym['st_size'] and sym['st_info']['type'] == 'STT_FUNC':
                for segment in elf.iter_segments():
                    if segment['p_type'] != 'PT_LOAD':
                        continue
                    offset = sym['st_value'] - segment['p_vaddr']
                    if 0 <= offset < segment['p_filesz']:
                        f.seek(segment['p_offset'] + offset)
                        code = f.read(min(sym['st_size'], 12000))
                        for instruction in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, sym['st_value']):
                            print(hex(instruction.address), instruction.mnemonic, instruction.op_str)
                        break
