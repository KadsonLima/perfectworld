"""Execute patched x86 instructions in isolation; never touch live city data."""
import struct
import sys
from pathlib import Path
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / (sys.argv[1] if len(sys.argv) > 1 else 'runtime/patches-tw6') / 'gdeliveryd'
TEST_BATTLE_SECONDS = 10800
sys.path.insert(0, str(ROOT / 'runtime/test-deps'))
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *


def machine(now):
    cpu = Uc(UC_ARCH_X86, UC_MODE_32)
    cpu.mem_map(0x8048000, 0x700000)
    with BINARY.open('rb') as f:
        elf = ELFFile(f)
        for seg in elf.iter_segments():
            if seg['p_type'] == 'PT_LOAD':
                cpu.mem_write(seg['p_vaddr'], seg.data())
    cpu.mem_map(0x100000, 0x10000)
    cpu.reg_write(UC_X86_REG_ESP, 0x108000)
    cpu.reg_write(UC_X86_REG_EBP, 0x109000)
    cpu.mem_write(0x868fca4, struct.pack('<I', now))
    return cpu


def word(cpu, address):
    return struct.unpack('<I', cpu.mem_read(address, 4))[0]


for now in (1789788000, 1789948800, 1790553600):
    cpu = machine(now)
    cpu.mem_write(0x109000 - 0x16c, struct.pack('<I', 0x101000))
    cpu.reg_write(UC_X86_REG_ECX, 0x12345678)
    cpu.reg_write(UC_X86_REG_EFLAGS, 0x246)
    cpu.emu_start(0x8343e1b, 0x8343e2a)
    assert word(cpu, 0x10101c) == now + 300
    assert cpu.reg_read(UC_X86_REG_ESP) == 0x108000
    assert cpu.reg_read(UC_X86_REG_ECX) == 0x12345678
    assert cpu.reg_read(UC_X86_REG_EFLAGS) == 0x246
    # No weekly rollover, even when a manual round occurs before Wednesday.
    cpu.reg_write(UC_X86_REG_EBX, 0x101000)
    cpu.reg_write(UC_X86_REG_EAX, now + 86400 * 3)
    cpu.emu_start(0x8343e55, 0x8343e7c)
    assert word(cpu, 0x10101c) == now + 300

    # Full original call site now passes real time instead of the frozen clock.
    cpu.mem_write(0x109000 - 4, struct.pack('<I', now - 86400))
    cpu.mem_write(0x109000 + 8, struct.pack('<I', 0x102000))
    cpu.emu_start(0x83424a2, 0x8341e82)
    sp = cpu.reg_read(UC_X86_REG_ESP)
    assert word(cpu, sp + 4) == 0x102000
    assert word(cpu, sp + 8) == now

    for current, expected_ip in ((now + 299, 0x8342417), (now + 300, 0x83422ba), (now + 301, 0x83422ba)):
        cpu.reg_write(UC_X86_REG_EAX, now + 300)
        cpu.mem_write(0x109000 + 12, struct.pack('<I', current))
        cpu.emu_start(0x83422b1, 0, count=2)
        assert cpu.reg_read(UC_X86_REG_EIP) == expected_ip

    # TestBattle writes the BattleStart end timestamp before the delivery's
    # 4h fighting watchdog (OnBattleStart: now + 14400) can cancel the city.
    cpu = machine(now)
    cpu.reg_write(UC_X86_REG_EAX, now)
    cpu.emu_start(0x834441c, 0x8344424)
    assert cpu.reg_read(UC_X86_REG_EAX) == now + TEST_BATTLE_SECONDS < now + 14400

    # TestBattle hook: fills challenger/battle_time and leaves the global TW
    # state (BattleManager+0x18: initialized/bidding/map loaded) untouched.
    for flags in (0x9, 0xb, 0x29):
        cpu = machine(now)
        manager, city, frame = 0x103000, 0x104000, 0x109000
        cpu.mem_write(manager + 0x18, struct.pack('<I', flags))
        cpu.mem_write(frame + 8, struct.pack('<I', manager))
        cpu.mem_write(frame + 0x10, struct.pack('<I', 3))
        cpu.mem_write(frame - 0x14, struct.pack('<I', now))
        cpu.reg_write(UC_X86_REG_EDX, city)
        stubs = {0x833dd5c, 0x833dbea, 0x8050e7c}
        cpu.hook_add(UC_HOOK_CODE, lambda uc, addr, size, data: (
            uc.reg_write(UC_X86_REG_ESP, uc.reg_read(UC_X86_REG_ESP) + 4),
            uc.reg_write(UC_X86_REG_EIP, struct.unpack('<I', uc.mem_read(uc.reg_read(UC_X86_REG_ESP) - 4, 4))[0]))
            if addr in stubs else None)
        cpu.mem_write(0x107ffc, struct.pack('<I', 0x8344418))
        cpu.reg_write(UC_X86_REG_ESP, 0x107ffc)
        cpu.emu_start(0x8663ec0, 0x8344418)
        assert word(cpu, manager + 0x18) == flags
        assert word(cpu, city + 0x10) == 3 and word(cpu, city + 0x1c) == now
        assert cpu.reg_read(UC_X86_REG_ESP) == 0x108000

print('OK: x86 schedules +300s, test battles end before the 4h watchdog, TestBattle keeps the TW state flags, skips weekly rollover, uses real time and starts at the deadline.')
