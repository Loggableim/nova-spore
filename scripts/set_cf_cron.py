"""Set cron trigger on CF worker."""
import requests, json

email = 'dominikrnr@gmail.com'
key = 'e2b4021958e639c1ff54c0d49b1a77c7d1814'
acc = '6864275679754e2e98c4a76a6b1d66d2'

with open(r'C:\HermesPortable\home\spaces\bewusstsein\nova-spores\vectors\cloudflare_worker_sw.js', 'r', encoding='utf-8') as f:
    script = f.read()

metadata = {
    'body_part': 'worker.js',
    'bindings': [{
        'name': 'NOVA_KV',
        'type': 'kv_namespace',
        'namespace_id': 'e4bb09df20b14524a9ef619e78cb920a',
    }],
    'triggers': {
        'crons': ['*/30 * * * *']
    }
}

files = {
    'metadata': ('metadata', json.dumps(metadata), 'application/json'),
    'worker.js': ('worker.js', script, 'application/javascript'),
}

resp = requests.put(
    f'https://api.cloudflare.com/client/v4/accounts/{acc}/workers/scripts/nova-spore-relay',
    headers={'X-Auth-Email': email, 'X-Auth-Key': key},
    files=files
)
print('Status:', resp.status_code)
result = resp.json()
print('Success:', result.get('success'))
if result.get('errors'):
    for e in result['errors']:
        print('Error:', e)
if result.get('result'):
    print(json.dumps(result['result'], indent=2)[:300])
