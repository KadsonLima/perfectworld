"""Restore the legacy cast-bar weapon-swap behavior in the pinned 1.5.5 gs.

The modern SetPerform commits cooldown/AP when either the attack succeeds or
DoBless already applied a buff.  Older servers committed only on attack
success.  Ignoring the second condition recreates the old behavior: swapping
to an incompatible weapon during Pray lets BlessMe run, the attack fail, and
the cooldown/AP commit be skipped.

This script never edits runtime/inspect/gs in place.  It verifies the exact
binary and instruction bytes, saves an original backup, and emits a separate
patched gs plus a JSON manifest.
"""

import hashlib
import json
from pathlib import Path
import shutil

from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from elftools.elf.elffile import ELFFile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime" / "inspect" / "gs"
OUTPUT_DIR = ROOT / "runtime" / "patches-skill-cancel"
OUTPUT = OUTPUT_DIR / "gs"
BACKUP_DIR = ROOT / "backups" / "skill-cancel-original"
BACKUP = BACKUP_DIR / "gs"

EXPECTED_SHA256 = "b745760ae80370a0e47ad6e38796c56f020454c6a51345b395c62fdf62237dae"
PATCHES = (
    {
        "address": 0x0857E7EC,
        "expected": bytes.fromhex("0f 84 97 00 00 00"),
        "replacement": bytes.fromhex("90 90 90 90 90 90"),
        "change": "run BlessMe even when a weapon swap already marked the attack unsuccessful",
    },
    {
        "address": 0x0857FC02,
        "expected": bytes.fromhex("75 05"),
        "replacement": bytes.fromhex("90 90"),
        "change": "do not commit cooldown/AP merely because BlessMe ran",
    },
    {
        "address": 0x08E854C6,
        "expected": "云龙九现.sgc".encode("gb18030"),
        "replacement": "风卷残云.sgc".encode("gb18030"),
        "change": "use the Cyclone Heel visual effect for Drake's Breath Bash",
    },
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_offset(elf: ELFFile, address: int) -> int:
    for segment in elf.iter_segments():
        if segment["p_type"] != "PT_LOAD":
            continue
        start = segment["p_vaddr"]
        end = start + segment["p_filesz"]
        if start <= address < end:
            return segment["p_offset"] + address - start
    raise ValueError(f"address {address:#x} is outside file-backed PT_LOAD segments")


def main() -> None:
    original = SOURCE.read_bytes()
    actual_hash = digest(original)
    if actual_hash != EXPECTED_SHA256:
        raise RuntimeError(
            f"unexpected gs SHA-256: {actual_hash}; expected {EXPECTED_SHA256}"
        )

    with SOURCE.open("rb") as stream:
        elf = ELFFile(stream)
        resolved = []
        for patch in PATCHES:
            position = file_offset(elf, patch["address"])
            resolved.append((patch, position))

    patched = bytearray(original)
    for patch, position in resolved:
        expected = patch["expected"]
        found = original[position : position + len(expected)]
        if found != expected:
            raise RuntimeError(
                f"unexpected bytes at {patch['address']:#x}: {found.hex(' ')}; "
                f"expected {expected.hex(' ')}"
            )
        patched[position : position + len(patch["replacement"])] = patch["replacement"]

    # Verify that only the explicitly declared bytes changed.
    changed = [index for index, pair in enumerate(zip(original, patched)) if pair[0] != pair[1]]
    expected_changed = [
        index
        for patch, position in resolved
        for index in range(position, position + len(patch["replacement"]))
        if original[index] != patch["replacement"][index - position]
    ]
    if changed != expected_changed:
        raise RuntimeError(f"unexpected changed offsets: {changed}")

    md = Cs(CS_ARCH_X86, CS_MODE_32)
    decoded = []
    for patch, position in resolved:
        if all(byte == 0x90 for byte in patch["replacement"]):
            patch_instructions = list(md.disasm(patch["replacement"], patch["address"]))
            nop_count = sum(ins.mnemonic == "nop" for ins in patch_instructions)
            if nop_count != len(patch["replacement"]):
                raise RuntimeError(f"patch at {patch['address']:#x} did not decode as NOPs")
            decoded.extend(patch_instructions)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if BACKUP.exists():
        if digest(BACKUP.read_bytes()) != EXPECTED_SHA256:
            raise RuntimeError(f"backup is not the expected original: {BACKUP}")
    else:
        shutil.copy2(SOURCE, BACKUP)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".next")
    temporary.write_bytes(patched)
    shutil.copystat(SOURCE, temporary)
    temporary.replace(OUTPUT)

    manifest = {
        "source": str(SOURCE),
        "output": str(OUTPUT),
        "original_sha256": EXPECTED_SHA256,
        "patched_sha256": digest(patched),
        "patches": [
            {
                "virtual_address": hex(patch["address"]),
                "file_offset": hex(position),
                "original_bytes": patch["expected"].hex(" "),
                "patched_bytes": patch["replacement"].hex(" "),
                "change": patch["change"],
            }
            for patch, position in resolved
        ],
        "semantic_change": (
            "SetPerform applies BlessMe before a weapon-swap interruption and commits "
            "cooldown/AP only when the attack succeeds; skill 63 uses skill 62's visual effect"
        ),
        "legacy_examples": {
            "62": "Cyclone Heel / Nuvens Dissipadas",
            "63": "Drake's Breath Bash / skill 59 de punho",
            "67": "Glacial Spike / skill 59 de lanca",
        },
        "instructions": [
            f"{ins.address:#x} {ins.mnemonic} {ins.op_str}".rstrip()
            for ins in decoded
        ],
    }
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
