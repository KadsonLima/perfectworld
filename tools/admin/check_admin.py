"""Read-only integration checks against the running local panel."""
import json
import re
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:8090'


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=40) as response:
        return json.load(response)


def post(path, data, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['X-CSRF-Token'] = token
    req = urllib.request.Request(BASE + path, json.dumps(data).encode(), headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


with urllib.request.urlopen(BASE, timeout=10) as response:
    html = response.read().decode()
token = re.search(r"const csrf='([^']+)'", html)[1]
before = get('/api/data')
assert len(get('/api/status')) == 11
assert len(before['cities']) == 52
assert post('/api/probe', {})[0] == 403
assert 'Abrir lances' in html and 'Fechar lances' in html
assert get('/api/tw_status')['mode'] in ('open', 'close', 'auto', 'unknown')
assert post('/api/bids', {'action': 'open'})[0] == 403
assert post('/api/bids', {'action': 'invalid'}, token)[0] == 400
assert post('/api/probe', {}, token)[0] == 200
assert post('/api/service', {'service': 'invalid', 'action': 'restart'}, token)[0] == 400
assert post('/api/tw', {'city': 1, 'attacker': 1, 'defender': 1, 'assign_owner': True}, token)[0] == 400
missing = 2147483647
existing = {int(row['fid']) for row in before['factions']}
while missing in existing or missing - 1 in existing:
    missing -= 2
code, result = post('/api/tw', {'city': 1, 'attacker': missing, 'defender': missing - 1, 'assign_owner': True}, token)
assert code == 400 and 'clas' in result['error'], result
after = get('/api/data')
assert [(row['id'], row['owner']) for row in before['cities']] == [(row['id'], row['owner']) for row in after['cities']]
req = urllib.request.Request(BASE, headers={'Host': 'example.com:8090'})
try:
    urllib.request.urlopen(req)
    raise AssertionError('Host externo aceito')
except urllib.error.HTTPError as error:
    assert error.code == 403
print('OK: painel, consultas, protocolo TW, CSRF, Host e validacoes sem alterar territorios.')
