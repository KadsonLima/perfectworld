"""Prepare a backed-up elements.data with configurable HP for both TW crystals."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'runtime/inspect/tw-elements-live.data'
OUTPUT = ROOT / 'runtime/tw-balance'
BACKUP = ROOT / 'backups/tw-crystal'


def crystal_fields(data):
    version = struct.unpack_from('<H', data)[0]
    if version != 156:
        raise ValueError('Expected server elements version 156')
    lines = (Path(__file__).parent / 'elements-v156.cfg').read_text(encoding='utf-8-sig').splitlines()
    i, pos, index = 2, 4, 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        name, offset, fields, types = lines[i:i+4]
        i += 4
        if offset == 'AUTO':
            assert index == 20
            pos += 12 + struct.unpack_from('<I', data, pos+4)[0]
        else:
            pos += int(offset)
        count = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        assert count < 100000
        fields, types = fields.split(';'), types.split(';')
        sizes = [int(t.split(':')[1]) if ':' in t else
                 {'int32':4, 'float':4, 'int16':2, 'int64':8}[t] for t in types]
        assert len(fields) == len(types)
        stride = sum(sizes)
        assert pos + count * stride <= len(data)
        if name.endswith('MONSTER_ESSENCE'):
            offsets = {f: sum(sizes[:n]) for n, f in enumerate(fields)}
            result = []
            for n in range(count):
                start = pos + n * stride
                ident = struct.unpack_from('<i', data, start + offsets['ID'])[0]
                if ident not in (10027, 10028):
                    continue
                def integer(field):
                    return struct.unpack_from('<i', data, start + offsets[field])[0]
                name_pos = start + offsets['Name']
                assert data[name_pos:name_pos+64].decode('utf-16le').split('\0')[0] == 'HQ Crystal'
                assert integer('role_in_war') == 1
                assert integer('faction') == {10027:2048, 10028:4096}[ident]
                assert integer('hp_adjust_common_value') == 0
                result.append((ident, start + offsets['life'], integer('life')))
            assert {r[0] for r in result} == {10027, 10028}
            return result
        pos += count * stride
        index += 1
    raise ValueError('Monster list not found')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--hp', type=int, default=12000000)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    if not 1 <= args.hp <= 2147483647:
        parser.error('HP must be a positive int32')
    SOURCE, OUTPUT = args.source, args.output
    original = SOURCE.read_bytes()
    edited = bytearray(original)
    changes = []
    for ident, offset, hp in crystal_fields(original):
        assert hp > 0, f'Invalid crystal HP: {hp}'
        struct.pack_into('<i', edited, offset, args.hp)
        changes.append({'id': ident, 'offset': offset, 'before': hp, 'after': args.hp})
    # Verify by parsing the result, then restore just the edited fields: every
    # other byte (including catapults, towers and unrelated monsters) must match.
    assert all(hp == args.hp for _, _, hp in crystal_fields(edited))
    restored = bytearray(edited)
    for change in changes:
        struct.pack_into('<i', restored, change['offset'], change['before'])
    assert restored == original
    BACKUP.mkdir(parents=True, exist_ok=True)
    original_hash = hashlib.sha256(original).hexdigest()
    backup = BACKUP / f'elements-{original_hash}.data'
    if backup.exists():
        assert backup.read_bytes() == original
    else:
        backup.write_bytes(original)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / 'elements.data'
    if target.exists():
        assert target.read_bytes() == edited, 'Output differs; do not overwrite a mounted file'
    else:
        target.write_bytes(edited)
    report = {'backup': str(backup), 'source_sha256': original_hash,
              'patched_sha256': hashlib.sha256(edited).hexdigest(), 'changes': changes}
    (OUTPUT / 'crystal-hp.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
