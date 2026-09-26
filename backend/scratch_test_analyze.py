import urllib.request
import json
import time

data = {
    'routes': [
        {
            'route_id': 'route_1',
            'geometry': {
                'type': 'LineString',
                'coordinates': [[77.6271, 12.9279], [77.6350, 12.9350], [77.6450, 12.9400], [77.6550, 12.9450]]
            }
        },
        {
            'route_id': 'route_2',
            'geometry': {
                'type': 'LineString',
                'coordinates': [[77.6271, 12.9279], [77.6300, 12.9300], [77.6400, 12.9380], [77.6550, 12.9450]]
            }
        },
        {
            'route_id': 'route_3',
            'geometry': {
                'type': 'LineString',
                'coordinates': [[77.6271, 12.9279], [77.6280, 12.9350], [77.6380, 12.9420], [77.6550, 12.9450]]
            }
        }
    ]
}

req = urllib.request.Request(
    'http://127.0.0.1:8000/api/features/analyze',
    data=json.dumps(data).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=45) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        t1 = time.time()
        print(f"Done in {t1-t0:.2f}s! Status: {resp.status}")
        for r in res['routes']:
            print(f"{r['route_id']}: safety_score={r.get('route_safety_score')}, segments={len(r.get('segments', []))}")
except Exception as e:
    print('Error:', e)
