#!/usr/bin/env python3
"""Give skill 63 the same client-side SGC effect as skill 62."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


CLIENT = Path(r"D:\Perfect World International 155 v159\element\elementskill.dll")
BACKUP = Path(r"D:\PW SERVER\perfectworld\backups\skill-animation\elementskill.dll")
MANIFEST = Path(r"D:\PW SERVER\perfectworld\runtime\patches-skill-cancel\client-animation.json")
OLD_EFFECT = "云龙九现.sgc".encode("gb18030")
NEW_EFFECT = "风卷残云.sgc".encode("gb18030")
EXPECTED_OCCURRENCES = 3


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    if len(OLD_EFFECT) != len(NEW_EFFECT):
        raise RuntimeError("effect names must have the same encoded length")

    current = CLIENT.read_bytes()
    old_count = current.count(OLD_EFFECT)
    new_count = current.count(NEW_EFFECT)

    if old_count == 0:
        if new_count < EXPECTED_OCCURRENCES:
            raise RuntimeError("client contains neither the expected original nor patched effects")
        patched = current
        status = "already_patched"
    else:
        if old_count != EXPECTED_OCCURRENCES:
            raise RuntimeError(
                f"expected {EXPECTED_OCCURRENCES} skill-63 effect references, found {old_count}"
            )
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        if not BACKUP.exists():
            shutil.copy2(CLIENT, BACKUP)

        patched = current.replace(OLD_EFFECT, NEW_EFFECT)
        if patched.count(OLD_EFFECT) != 0:
            raise RuntimeError("not all skill-63 effect references were replaced")

        temporary = CLIENT.with_suffix(".dll.next")
        temporary.write_bytes(patched)
        temporary.replace(CLIENT)
        status = "patched"

    manifest = {
        "status": status,
        "client": str(CLIENT),
        "backup": str(BACKUP),
        "original_sha256": sha256(BACKUP.read_bytes()) if BACKUP.exists() else None,
        "patched_sha256": sha256(patched),
        "replacements": EXPECTED_OCCURRENCES,
        "old_effect": OLD_EFFECT.hex(" "),
        "new_effect": NEW_EFFECT.hex(" "),
        "scope": "skill 63 normal and cultivation variants",
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
