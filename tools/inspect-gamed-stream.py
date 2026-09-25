"""Read selected configs from the pinned game layer, without executing it.

Limit transfer to the declared layer size. Partial stream is not digest-verified.
"""
import json
from pathlib import Path
import tarfile
import urllib.request

root = Path(__file__).resolve().parents[1]
folder = root / 'audit/images/gamed'
manifest = json.loads((folder / 'manifest.json').read_text())
repo = 'ossperfectworld/perfect-world-gamed'
with urllib.request.urlopen('https://auth.docker.io/token?service=registry.docker.io&scope=repository:' + repo + ':pull', timeout=15) as response:
    token = json.load(response)['token']
layer = max(manifest['layers'], key=lambda item: item['size'])
request = urllib.request.Request('https://registry-1.docker.io/v2/' + repo + '/blobs/' + layer['digest'], headers={'Authorization': 'Bearer ' + token})

class Limited:
    def __init__(self, stream):
        self.stream = stream
        self.count = 0
    def read(self, size=-1):
        if size < 0:
            raise RuntimeError('Unbounded read')
        size = min(size, layer['size'] - self.count)
        if size <= 0:
            return b''
        data = self.stream.read(size)
        self.count += len(data)
        if self.count % (100 * 1024 * 1024) < len(data):
            print('TRANSFER MiB:', self.count // (1024 * 1024), flush=True)
        return data

wanted = {'gs.conf', 'gsalias.conf'}
with urllib.request.urlopen(request, timeout=15) as response:
    stream = Limited(response)
    with tarfile.open(fileobj=stream, mode='r|gz') as archive:
        for index, member in enumerate(archive):
            path = Path(member.name.lstrip('/'))
            if index < 3:
                print('MEMBER', member.name, member.size, flush=True)
            if member.isfile() and member.size < 1_000_000 and '..' not in path.parts and (path.name in wanted or (path.suffix in {'.conf', '.cfg'} and 'config' in path.parts)):
                dest = folder / 'stream-files' / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.extractfile(member).read())
                if path.name in wanted:
                    print('CONFIG', member.name, flush=True)
                wanted.discard(path.name)
            if not wanted:
                print('Found both main configs; transferred bytes:', stream.count, flush=True)
                break
