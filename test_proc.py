import requests

base = 'http://localhost:8000/api'

requests.post(f'{base}/stations/rain', json={'name':'城东雨量站','code':'RAIN001','district':'城东区','longitude':120.15,'latitude':30.28,'elevation':4.5})
requests.post(f'{base}/pump/stations', json={'name':'城东泵站','code':'PUMP001','district':'城东区','longitude':120.15,'latitude':30.28,'design_capacity':500,'status':'stopped'})
requests.post(f'{base}/materials/warehouses', json={'name':'城东仓储点A','district':'城东区','longitude':120.17,'latitude':30.30})
requests.post(f'{base}/materials/warehouses', json={'name':'城西仓储点','district':'城西区','longitude':120.05,'latitude':30.25})
for wid in [1, 2]:
    for mt in ['water_pump', 'sandbag', 'assault_boat']:
        qty = 10 if mt == 'water_pump' else (200 if mt == 'sandbag' else 2)
        safe = 20 if mt == 'water_pump' else (500 if mt == 'sandbag' else 10)
        requests.post(f'{base}/materials/inventories', json={'warehouse_id':wid,'material_type':mt,'quantity':qty,'safety_stock':safe,'locked_quantity':0})

from database import SessionLocal
from models import PipeNetwork, GroundElevation
db = SessionLocal()
db.add(PipeNetwork(district='城东区', total_capacity=10000, current_usage=7500))
db.add(GroundElevation(district='城东区', area_name='低洼片区', longitude=120.15, latitude=30.28, elevation=3.5, drainage_grade='P1'))
db.commit()
db.close()

requests.post(f'{base}/stations/rain-data', json={'station_id':1,'rainfall_1h':50,'rainfall_3h':100,'rainfall_6h':150,'rainfall_24h':200})
requests.post(f'{base}/materials/check-inventory')

r = requests.get(f'{base}/system/replenishment-requests')
reqs = r.json()
if reqs:
    req_id = reqs[0]['id']
    print(f'补货申请ID={req_id}')
    requests.put(f'{base}/materials/replenishment/{req_id}/approve-district', params={'approver':'赵区级'})
    requests.put(f'{base}/materials/replenishment/{req_id}/approve-city', params={'approver':'钱市级'})

    r = requests.get(f'{base}/system/procurements', params={'request_id': req_id})
    procs = r.json()
    print(f'采购记录: {len(procs)}条')
    if procs:
        proc_id = procs[0]['id']
        status = procs[0]['status']
        qty = procs[0]['quantity']
        print(f'采购ID={proc_id} 状态={status} 数量={qty}')

        print('调用arrive...')
        r = requests.put(f'{base}/system/procurements/{proc_id}/arrive')
        print(f'arrive状态码: {r.status_code}')
        print(f'arrive响应: {r.text[:500]}')

        if r.status_code == 200:
            print('调用store...')
            r2 = requests.put(f'{base}/system/procurements/{proc_id}/store')
            print(f'store状态码: {r2.status_code}')
            print(f'store响应: {r2.text[:500]}')
