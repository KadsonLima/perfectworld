"""Read image metadata and small text layers without executing image code."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'audit' / 'images'
OUT.mkdir(parents=True, exist_ok=True)

def get(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=15) as response:
        return response.read()

names = sys.argv[1:] or ['authd', 'gacd', 'gamed', 'gamedbd', 'gdeliveryd', 'gfactiond', 'glinkd', 'logservice', 'uniquenamed', 'website-register']
lockfile = OUT / 'images.lock.json'
lock = json.loads(lockfile.read_text()) if lockfile.exists() else {}
for name in names:
    repo = 'ossperfectworld/perfect-world-' + name
    token = json.loads(get('https://auth.docker.io/token?service=registry.docker.io&scope=repository:' + repo + ':pull'))['token']
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.docker.distribution.manifest.v2+json'}
    base = 'https://registry-1.docker.io/v2/' + repo
    raw = get(base + '/manifests/latest', headers)
    manifest = json.loads(raw)
    digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
    lock[name] = repo + '@' + digest
    lockfile.write_text(json.dumps(lock, indent=2) + '\n')
    target = OUT / name
    target.mkdir(exist_ok=True)
    (target / 'manifest.json').write_bytes(raw)
    config = get(base + '/blobs/' + manifest['config']['digest'], headers)
    (target / 'image-config.json').write_bytes(config)
    parsed = json.loads(config)
    print(name, parsed.get('architecture'), parsed.get('config', {}).get('Cmd'), flush=True)
    for layer in manifest['layers']:
        # Avoid downloading game assets/base OS; inspect small configuration layers.
        if layer['size'] > 100_000:
            continue
        try:
            blob = get(base + '/blobs/' + layer['digest'], headers)
        except (TimeoutError, OSError) as error:
            print('LAYER NOT INSPECTED:', name, layer['digest'], str(error), flush=True)
            continue
        if 'sha256:' + hashlib.sha256(blob).hexdigest() != layer['digest']:
            raise RuntimeError('Layer digest mismatch')
        with tarfile.open(fileobj=io.BytesIO(blob), mode='r:*') as archive:
            for member in archive:
                path = Path(member.name)
                if not member.isfile() or member.size > 1_000_000 or path.is_absolute() or '..' in path.parts:
                    continue
                if path.suffix.lower() not in {'.sh', '.conf', '.cfg', '.ini', '.xml', '.php', '.properties', '.tmpl'}:
                    continue
                data = archive.extractfile(member).read()
                if b'\0' in data:
                    continue
                dest = target / 'files' / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
    (OUT / 'images.lock.json').write_text(json.dumps(lock, indent=2) + '\n')
