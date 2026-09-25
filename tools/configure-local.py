"""Apply reviewed local adjustments, preserving every changed upstream file."""
import datetime
import json
from pathlib import Path
import secrets
import re
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
backup = root / 'backups' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
backup.mkdir(parents=True)
for relative in ['docker-compose.yaml', 'Makefile', 'sql/db.sql']:
    dest = backup / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / relative, dest)
compose = json.loads(subprocess.check_output(['docker', 'compose', 'config', '--no-interpolate', '--format', 'json'], cwd=root))
lock = json.loads((root / 'audit/images/images.lock.json').read_text())
compose['name'] = '${COMPOSE_PROJECT_NAME:-perfectworld}'
for value in compose['volumes'].values():
    value.pop('name', None)
compose['networks']['infrastructure'].pop('name', None)
services = compose['services']
for service, spec in services.items():
    name = service.removeprefix('perfectworld-')
    spec.pop('container_name', None)
    spec['restart'] = 'unless-stopped'
    spec['logging'] = {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '3'}}
    env = spec.get('environment', {})
    env['TZ'] = '${TZ:-America/Montevideo}'
    for key in ['MYSQL_PASSWORD', 'MYSQL_ROOT_PASSWORD']:
        if key in env:
            env[key] = '${MYSQL_ROOT_PASSWORD:?Defina MYSQL_ROOT_PASSWORD no .env}'
    if name == 'db':
        env['MYSQL_ROOT_HOST'] = '%'
        env.pop('MYSQL_USER', None)
        env.pop('MYSQL_PASSWORD', None)
        spec['healthcheck'] = {'test': ['CMD-SHELL', 'MYSQL_PWD="$$MYSQL_ROOT_PASSWORD" mysql -h 127.0.0.1 -u root pw -Nse "SELECT COUNT(*) FROM users" >/dev/null'], 'interval': '10s', 'timeout': '5s', 'retries': 18, 'start_period': '60s'}
        for mount in spec['volumes']:
            if mount['target'] == '/docker-entrypoint-initdb.d':
                mount['read_only'] = True
        continue
    spec['image'] = lock[name]
    config = json.loads((root / 'audit/images' / name / 'image-config.json').read_text())
    spec['platform'] = 'linux/' + config['architecture']
    if name == 'website-register':
        spec['ports'] = ['${PW_BIND_IP:-127.0.0.1}:${PW_REGISTER_PORT:-8080}:80']
        spec['depends_on'] = {'perfectworld-db': {'condition': 'service_healthy'}}
        continue
    volume = 'pw-' + name + '-home'
    compose['volumes'][volume] = {}
    spec.setdefault('volumes', []).append({'type': 'volume', 'source': volume, 'target': '/home'})
    original = root / 'audit/images' / name / 'files/home/entrypoint.sh'
    text = original.read_text()
    text = text.replace('RUN ln ', 'ln ')
    text = text.replace('chmod -R 755 /home\n', '')
    text = text.replace('#!/bin/bash', '#!/bin/sh\nset -eu')
    dest = root / 'configs' / name / 'entrypoint.sh'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, newline='\n')
    spec['volumes'].append({'type': 'bind', 'source': './configs/' + name + '/entrypoint.sh', 'target': '/home/entrypoint.sh', 'read_only': True})
    for template in original.parent.glob('*.tmpl'):
        shutil.copy2(template, dest.parent / template.name)
        spec['volumes'].append({'type': 'bind', 'source': './configs/' + name + '/' + template.name, 'target': '/home/' + template.name, 'read_only': True})
        for variable in re.findall(r'\$([A-Z][A-Z_0-9]*)', template.read_text(errors='replace')):
            canonical = variable.replace('LOG_SERVICE_', 'LOGSERVICE_')
            if canonical in env and variable not in env:
                env[variable] = env[canonical]
            if variable not in env:
                raise RuntimeError('Missing template variable: ' + name + ': ' + variable)
    if name == 'gamedbd':
        # Upstream template uses /home/backup, not /home/backupwdb.
        for mount in spec['volumes']:
            if mount['target'] == '/home/backupwdb':
                mount['target'] = '/home/backup'
    spec.setdefault('depends_on', {})['perfectworld-db'] = {'condition': 'service_healthy'}
    if name == 'glinkd':
        spec['ports'] = ['${PW_BIND_IP:-127.0.0.1}:${PW_GAME_PORT:-29000}:29000']
    if name == 'gamed':
        start = (root / 'audit/images/gamed/files/home/start.sh').read_text().splitlines()[1].strip()
        if not start.startswith('./gs ') or not start.endswith(' &'):
            raise RuntimeError('Unexpected upstream start command')
        (dest.parent / 'start.sh').write_text('#!/bin/sh\nset -eu\ncd /home\nexec ' + start[:-2] + '\n', newline='\n')
        spec['command'] = ['sh', '/home/start.sh']
        spec['volumes'].append({'type': 'bind', 'source': './configs/gamed/start.sh', 'target': '/home/start.sh', 'read_only': True})
sql = (root / 'sql/db.sql').read_text()
sql = sql.replace('DROP DATABASE IF EXISTS pw;', '-- No database deletion: initialization runs only on an empty MySQL volume.')
sql = sql.replace('CREATE DATABASE pw ', 'CREATE DATABASE IF NOT EXISTS pw ')
sql = sql.replace('reason1, gmroleid);', 'reason1, gmroleid1);')
sql = sql.replace('ipmask3, enable1) VALUES', 'ipmask3, enable) VALUES')
sql = sql.replace('birthday = birthda1', 'birthday = birthday1')
(root / 'sql/db.sql').write_text(sql, newline='\n')
(root / 'docker-compose.yaml').write_text(json.dumps(compose, indent=2) + '\n', newline='\n')
(root / 'Makefile').write_text('up-perfectworld:\n\tdocker compose up -d\n\ndown-perfectworld:\n\tdocker compose down\n', newline='\n')
envfile = root / '.env'
if not envfile.exists():
    envfile.write_text('COMPOSE_PROJECT_NAME=perfectworld\nPW_BIND_IP=127.0.0.1\nPW_GAME_PORT=29000\nPW_REGISTER_PORT=8080\nTZ=America/Montevideo\nMYSQL_ROOT_PASSWORD=' + secrets.token_hex(24) + '\n', newline='\n')
print('Backups:', backup)
