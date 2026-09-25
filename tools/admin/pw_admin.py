"""Local Docker administration and native 1.5.5 TW test integration."""
from __future__ import annotations
import base64
import csv
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'runtime' / 'admin'
RUNTIME.mkdir(parents=True, exist_ok=True)
CSRF = secrets.token_urlsafe(32)
MUTATION = threading.Lock()
SERVICES = tuple('perfectworld-' + s for s in ('db', 'logservice', 'uniquenamed', 'authd', 'gamedbd', 'gacd', 'gfactiond', 'gdeliveryd', 'glinkd', 'gamed', 'website-register'))
PIN = '702e8e2da7816e73528d444af0ef7248e7f13a5e46e10a58207c72299ceadb25'


def docker(*args, stdin=None, timeout=35):
    result = subprocess.run(['docker', 'compose', *map(str, args)], cwd=ROOT,
                            input=stdin, capture_output=True, timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    out = result.stdout.decode('utf-8', errors='replace')
    if result.returncode:
        raise ValueError(result.stderr.decode('utf-8', errors='replace')[-2500:] or out[-2500:])
    return out


def table(command):
    if command not in ('listcity', 'listfaction', 'listrolebrief'):
        raise ValueError('Consulta invalida')
    output = docker('exec', '-T', '-w', '/home', 'perfectworld-gamedbd', './gamedbd', 'gamesys.conf', command)
    lines = output.splitlines()
    header = next((i for i, line in enumerate(lines) if line.startswith(('id,level,owner,', 'fid,name,', 'roleid,userid,'))), None)
    if header is None:
        raise ValueError('Servidor nao retornou a tabela esperada')
    return [row for row in csv.DictReader(io.StringIO('\n'.join(lines[header:])))
            if (row.get('id') or row.get('fid') or row.get('roleid') or '').isdigit()]


def debug(mode, text):
    source = (Path(__file__).parent / 'rpc.php').read_text(encoding='utf-8').removeprefix('<?php')
    encoded = base64.b64encode(source.encode()).decode()
    # Argument arrays preserve PHP expressions and IDs without shell interpolation.
    return docker('exec', '-T', 'perfectworld-website-register', 'php', '-r',
                  'array_shift($argv); eval(base64_decode($argv[0]));', encoded, mode, text)


def positive(value, name):
    if isinstance(value, bool) or not str(value).isdigit() or not 1 <= int(value) <= 2147483647:
        raise ValueError(f'{name}: ID invalido')
    return int(value)


def non_negative(value, name):
    if isinstance(value, bool) or not str(value).isdigit() or not 0 <= int(value) <= 2147483647:
        raise ValueError(f'{name}: ID invalido')
    return int(value)


def status():
    output = docker('ps', '-a', '--format', 'json')
    rows = []
    for line in output.splitlines():
        item = json.loads(line)
        rows.extend(item if isinstance(item, list) else [item])
    return [{'service': row['Service'], 'state': row['State'], 'status': row['Status']} for row in rows]


def audit(record):
    record = {'time': datetime.now(timezone.utc).isoformat(), **record}
    with (RUNTIME / 'actions.jsonl').open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + '\n')


# Debug tag 1 calls BattleManager::SetForgedTime(seconds since Sunday).
# These values are fixed by the verified 1.5.5 ELF, not user supplied.
BID_TIMES = {'open': 327601, 'close': 416521, 'auto': 0}
TIMER_RE = re.compile(r'Timer update: \((\d+)\)')
BID_RE = re.compile(r'\b(beginbid|endbid):')
DELIVERY_HASHES = {
    '19f4081f407e1e6d0a398bb299d2efa3b43de284a7eca1ec85e31a5212a4f959',
    'c78bc4f1b8b2b499257d2b815def6bc1ff3e11ed79e459d44a64d871c3dcb250',
}


def delivery_boot():
    container = docker('ps', '-q', 'perfectworld-gdeliveryd').strip()
    if not container:
        raise ValueError('Delivery parado. Inicie o servico primeiro.')
    result = subprocess.run(['docker', 'inspect', '--format', '{{.State.StartedAt}}', container],
                            capture_output=True, timeout=15,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        raise ValueError('Nao foi possivel identificar a inicializacao do delivery')
    return result.stdout.decode().strip()


def bid_evidence(logs):
    timer = None
    state = None
    for line in logs.splitlines():
        match = TIMER_RE.search(line)
        if match:
            timer = int(match[1])
        match = BID_RE.search(line)
        if match:
            state = 1 if match[1] == 'beginbid' else 0
    return timer, state


def tw_status():
    boot = delivery_boot()
    logs = docker('logs', '--since', boot, '--tail', '10000',
                  'perfectworld-gdeliveryd', 'perfectworld-logservice')
    timer, state = bid_evidence(logs)
    mode = {327601: 'open', 416521: 'close', 0: 'auto'}.get(timer, 'unknown')
    # A forced time beyond BidMaxDuration + 120 cannot accept new bids.
    if mode == 'close':
        state = 0
    label = {1: 'Lances abertos', 0: 'Lances fechados'}.get(state, 'Estado dos lances ainda nao confirmado')
    modes = {'open': 'abertura manual', 'close': 'fechamento manual',
             'auto': 'agenda automatica', 'unknown': 'horario ainda nao confirmado'}
    return {'state': state, 'mode': mode, 'boot': boot,
            'message': f'{label} — {modes[mode]}.'}


def control_bids(data):
    action = data.get('action')
    if action not in BID_TIMES:
        raise ValueError('Acao de lances invalida')
    boot = delivery_boot()
    checksum = docker('exec', '-T', 'perfectworld-gdeliveryd', 'sha256sum', '/home/gdeliveryd').split()[0]
    if checksum not in DELIVERY_HASHES:
        raise ValueError('Binario delivery diferente da versao validada para controle de lances')
    before = tw_status()
    if before['mode'] == action and (action != 'open' or before['state'] == 1):
        return {'ok': True, 'message': before['message']}
    cities = table('listcity')
    if action == 'open' and before['state'] != 1:
        tests = RUNTIME / 'tw-tests.json'
        pending = json.loads(tests.read_text()) if tests.exists() else {}
        if any(int(c['challenger']) or int(c['status']) for c in cities) or any(
                v.get('expires', 0) > time.time() for v in pending.values()):
            raise ValueError('Ha disputa ou TW de teste em andamento. Aguarde sua conclusao antes de reabrir lances.')
    since = datetime.now(timezone.utc).isoformat()
    audit({'action': 'bids_requested', 'mode': action, 'boot': boot, 'before': before, 'cities': cities})
    debug('bidtime', str(BID_TIMES[action]))
    # The native BattleManager timer runs every 60 seconds. Confirm execution,
    # not merely socket delivery. On timeout retain the explicit uncertain state.
    deadline = time.monotonic() + 80
    while time.monotonic() < deadline:
        logs = docker('logs', '--since', since, '--tail', '3000',
                      'perfectworld-gdeliveryd', 'perfectworld-logservice')
        timer, state = bid_evidence(logs)
        clock_ok = timer == BID_TIMES[action]
        transition_ok = (action == 'auto' or
                         action == 'open' and (state == 1 or before['state'] == 1) or
                         action == 'close' and (state == 0 or before['state'] != 1))
        if clock_ok and transition_ok:
            if delivery_boot() != boot:
                raise ValueError('Delivery reiniciou durante a operacao; verifique o estado novamente')
            audit({'action': 'bids_confirmed', 'mode': action, 'boot': boot})
            messages = {'open': 'Lances abertos no modo manual. Feche pelo painel ao terminar.',
                        'close': 'Lances fechados. As TW desta rodada serao agendadas para 5 minutos apos o fechamento processado pelo servidor.',
                        'auto': 'Agenda automatica restaurada. Os lances seguem o horario normal do servidor.'}
            return {'ok': True, 'message': messages[action]}
        time.sleep(2)
    audit({'action': 'bids_unconfirmed', 'mode': action, 'boot': boot})
    raise ValueError('Comando enviado, mas sem confirmacao em 80 segundos. Verifique o estado antes de repetir; o comando pode ter sido aplicado.')


def probe():
    since = datetime.now(timezone.utc).isoformat()
    debug('probe', 'pw-admin-probe')
    for _ in range(5):
        logs = docker('logs', '--since', since, '--tail', '150', 'perfectworld-gdeliveryd')
        if 'DebugCommand: roleid=0 tag=999 size=14' in logs:
            return {'ok': True, 'message': 'Protocolo interno de TW confirmado pelo delivery.'}
        time.sleep(.4)
    raise ValueError('O delivery nao confirmou o protocolo interno')


def create_tw(data):
    city = positive(data.get('city'), 'Territorio')
    attacker = positive(data.get('attacker'), 'Cla atacante')
    defender = positive(data.get('defender'), 'Cla defensor')
    if attacker == defender:
        raise ValueError('Escolha dois clas diferentes')
    if data.get('assign_owner') is not True:
        raise ValueError('Confirme a atribuicao do territorio ao cla defensor')
    config = json.loads(docker('config', '--format', 'json'))
    if PIN not in config['services']['perfectworld-gamed']['image']:
        raise ValueError('Integracao validada somente para a imagem 1.5.5 fixada neste projeto')
    factions = {int(row['fid']) for row in table('listfaction')}
    if not {attacker, defender}.issubset(factions):
        raise ValueError('Crie os dois clas no jogo e atualize a lista antes de iniciar a TW')
    territory = next((row for row in table('listcity') if int(row['id']) == city), None)
    if territory is None:
        raise ValueError('Territorio inexistente')
    if int(territory['status']) != 0 or int(territory['challenger']) != 0:
        raise ValueError('O territorio ja tem uma disputa ou batalha registrada')
    active = [s for s in status() if s['state'] != 'running']
    if active:
        raise ValueError('Suba os servicos antes de iniciar a batalha')
    # The test command changes state in memory. Refuse duplicate starts across
    # browser refreshes even when the database still reports an idle territory.
    state_path = RUNTIME / 'tw-tests.json'
    states = json.loads(state_path.read_text()) if state_path.exists() else {}
    if states.get(str(city), {}).get('expires', 0) > time.time():
        raise ValueError('Ja existe uma solicitacao de TW de teste para este territorio; aguarde 24 horas')
    before = {'action': 'tw_before', 'city': city, 'attacker': attacker, 'defender': defender, 'territory': territory}
    audit(before)
    snapshot = RUNTIME / f'territory-{city}-{time.time_ns()}.json'
    snapshot.write_text(json.dumps(before, indent=2), encoding='utf-8')
    probe()
    debug('owner', f'{city}-{defender}')
    # SetOwner is applied by the delivery's internal timer and can take up to
    # ~60s to land in the persisted table (see docs/PW-ADMIN-LOCAL.md); a short
    # poll here made this time out on a change that was actually in flight.
    for _ in range(70):
        updated = next((row for row in table('listcity') if int(row['id']) == city), None)
        if updated and int(updated['owner']) == defender:
            break
        time.sleep(1)
    else:
        raise ValueError('A atribuicao do territorio nao foi confirmada; a batalha nao foi solicitada')
    # Reserve before scheduling: a timeout or refresh cannot cause a duplicate battle.
    start_at = time.time() + TEST_TW_DELAY
    states[str(city)] = {'expires': time.time() + 86400, 'attacker': attacker, 'defender': defender,
                         'state': 'scheduled', 'start_at': start_at}
    state_path.write_text(json.dumps(states), encoding='utf-8')
    audit({'action': 'tw_scheduled', 'city': city, 'attacker': attacker, 'start_at': start_at})
    schedule_test_battle(city, attacker, start_at)
    when = datetime.fromtimestamp(start_at).strftime('%H:%M:%S')
    return {'ok': True, 'message': f'Territorio {city} atribuido ao defensor. A TW de teste comeca em {TEST_TW_DELAY // 60} minutos (as {when}) e dura 24 horas. Acompanhe o resultado nos logs.'}


# TestBattle dispatches BattleStart to the gs immediately; the delay is applied here.
TEST_TW_DELAY = 180


def schedule_test_battle(city, attacker, start_at):
    timer = threading.Timer(max(0, start_at - time.time()), start_test_battle, (city, attacker))
    timer.daemon = True
    timer.start()


def start_test_battle(city, attacker):
    state_path = RUNTIME / 'tw-tests.json'
    with MUTATION:
        states = json.loads(state_path.read_text()) if state_path.exists() else {}
        entry = states.get(str(city))
        if not entry or entry.get('state') != 'scheduled':
            return
        since = datetime.now(timezone.utc).isoformat()
        entry['state'] = 'requested'
        state_path.write_text(json.dumps(states), encoding='utf-8')
        try:
            debug('battle', f'{city}-{attacker}')
            evidence = ''
            pattern = re.compile(rf'BattleStart_Re: retcode=(\d+) battle_id={city}\.')
            for _ in range(18):
                evidence = docker('logs', '--since', since, '--tail', '200', 'perfectworld-gdeliveryd')
                match = pattern.search(evidence)
                if match:
                    entry['state'] = 'accepted' if match[1] == '0' else 'rejected'
                    state_path.write_text(json.dumps(states), encoding='utf-8')
                    audit({'action': 'tw_result', 'city': city, 'retcode': int(match[1]), 'evidence': evidence[-5000:]})
                    return
                time.sleep(.5)
            audit({'action': 'tw_unconfirmed', 'city': city, 'evidence': evidence[-5000:]})
        except (ValueError, subprocess.TimeoutExpired, OSError) as exc:
            audit({'action': 'tw_error', 'city': city, 'error': str(exc)})


def resume_test_battles():
    """Re-arm test TWs scheduled before a panel restart; late ones start now."""
    state_path = RUNTIME / 'tw-tests.json'
    states = json.loads(state_path.read_text()) if state_path.exists() else {}
    for city, entry in states.items():
        if entry.get('state') == 'scheduled' and entry.get('expires', 0) > time.time():
            schedule_test_battle(int(city), entry['attacker'], entry.get('start_at', 0))


def set_owner(data):
    city = positive(data.get('city'), 'Territorio')
    owner = non_negative(data.get('owner'), 'Cla')
    territory = next((row for row in table('listcity') if int(row['id']) == city), None)
    if territory is None:
        raise ValueError('Territorio inexistente')
    if owner != 0:
        factions = {int(row['fid']) for row in table('listfaction')}
        if owner not in factions:
            raise ValueError('Cla inexistente; atualize a lista e tente novamente')
    audit({'action': 'set_owner_before', 'city': city, 'owner': owner, 'territory': territory})
    debug('owner', f'{city}-{owner}')
    for _ in range(20):
        time.sleep(1)
        updated = next((row for row in table('listcity') if int(row['id']) == city), None)
        if updated and int(updated['owner']) == owner:
            audit({'action': 'set_owner_result', 'city': city, 'owner': owner, 'confirmed': True})
            return {'ok': True, 'message': f'Territorio {city} atribuido ao cla {owner or "neutro"}.'}
    # The delivery applies this on an internal timer; it can land after this wait.
    audit({'action': 'set_owner_result', 'city': city, 'owner': owner, 'confirmed': False})
    return {'ok': True, 'message': f'Comando enviado para o territorio {city}. Pode levar ate 1 minuto para refletir; atualize os dados para conferir.'}


def advance_tw(data):
    city = positive(data.get('city'), 'Territorio')
    territory = next((row for row in table('listcity') if int(row['id']) == city), None)
    if territory is None:
        raise ValueError('Territorio inexistente')
    challenger = int(territory['challenger'])
    if challenger == 0:
        raise ValueError('Este territorio nao tem desafio pendente para adiantar')
    audit({'action': 'advance_tw_before', 'city': city, 'territory': territory})
    since = datetime.now(timezone.utc).isoformat()
    debug('battle', f'{city}-{challenger}')
    evidence = ''
    pattern = re.compile(rf'BattleStart_Re: retcode=(\d+) battle_id={city}\.')
    for _ in range(18):
        evidence = docker('logs', '--since', since, '--tail', '200', 'perfectworld-gdeliveryd')
        match = pattern.search(evidence)
        if match:
            audit({'action': 'advance_tw_result', 'city': city, 'retcode': int(match[1]), 'evidence': evidence[-5000:]})
            if match[1] != '0':
                raise ValueError(f'O servidor recusou adiantar a batalha: codigo {match[1]}.')
            return {'ok': True, 'message': f'TW {city} adiantada e aceita pelo servidor. Entre pelo NPC de guerra territorial agora.'}
        time.sleep(.5)
    audit({'action': 'advance_tw_unconfirmed', 'city': city, 'evidence': evidence[-5000:]})
    raise ValueError('Solicitacao enviada, mas sem confirmacao em 9 segundos. Consulte os logs antes de repetir.')


class Handler(BaseHTTPRequestHandler):
    def send(self, code, data, content_type='application/json; charset=utf-8'):
        body = data.encode() if isinstance(data, str) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def host_ok(self):
        return self.headers.get('Host') in ('127.0.0.1:8090', 'localhost:8090')

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, {'error': 'Acesso somente local'})
        try:
            if self.path == '/':
                html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8').replace('__CSRF__', CSRF)
                return self.send(200, html, 'text/html; charset=utf-8')
            if self.path == '/api/status':
                return self.send(200, status())
            if self.path == '/api/tw_status':
                return self.send(200, tw_status())
            if self.path == '/api/data':
                return self.send(200, {'factions': table('listfaction'), 'cities': table('listcity'),
                                       'roles': [r for r in table('listrolebrief') if int(r['roleid']) >= 1024]})
            if self.path == '/api/logs':
                return self.send(200, {'logs': docker('logs', '--tail', '100', 'perfectworld-gdeliveryd', 'perfectworld-gamed')[-25000:]})
            self.send(404, {'error': 'Nao encontrado'})
        except (ValueError, subprocess.TimeoutExpired, OSError) as exc:
            self.send(500, {'error': str(exc)})

    def do_POST(self):
        try:
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= 4096:
                raise ValueError('Requisicao invalida')
            body = self.rfile.read(size)
            if not self.host_ok() or not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), CSRF):
                return self.send(403, {'error': 'Recarregue o painel local'})
            data = json.loads(body)
            with MUTATION:
                if self.path == '/api/bids':
                    return self.send(200, control_bids(data))
                if self.path == '/api/probe':
                    return self.send(200, probe())
                if self.path == '/api/tw':
                    return self.send(200, create_tw(data))
                if self.path == '/api/set_owner':
                    return self.send(200, set_owner(data))
                if self.path == '/api/advance_tw':
                    return self.send(200, advance_tw(data))
                if self.path == '/api/service':
                    service, action = data.get('service'), data.get('action')
                    if service not in SERVICES or action not in ('start', 'stop', 'restart'):
                        raise ValueError('Servico ou acao invalida')
                    output = docker(action, service, timeout=60)
                    audit({'action': action, 'service': service})
                    return self.send(200, {'message': 'Comando concluido.', 'output': output})
                self.send(404, {'error': 'Nao encontrado'})
        except (ValueError, KeyError, TypeError, subprocess.TimeoutExpired, OSError) as exc:
            self.send(400, {'error': str(exc)})


if __name__ == '__main__':
    resume_test_battles()
    print('PW Admin local: http://127.0.0.1:8090', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8090), Handler).serve_forever()
