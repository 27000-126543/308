import requests, json
from datetime import datetime, timedelta, date

base = 'http://localhost:8000/api'

print('=== 初始化数据 ===')
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
r = requests.get(f'{base}/warnings')
wid = r.json()[0]['id']

requests.post(f'{base}/warnings/{wid}/trigger-resource-plan')
r = requests.get(f'{base}/materials/allocation-plans')
plan_id = r.json()[0]['id']
requests.put(f'{base}/materials/allocation-plans/{plan_id}/approve', params={'approver':'张指挥长'})

r = requests.get(f'{base}/materials/allocations', params={'plan_id': plan_id})
allocs = r.json()
if allocs:
    aid = allocs[0]['id']
    requests.put(f'{base}/materials/allocations/{aid}/ship')
    requests.put(f'{base}/materials/allocations/{aid}/arrive', params={'receiver':'李现场'})
    requests.put(f'{base}/materials/allocations/{aid}/consume', params={'consumed_quantity':5})

requests.post(f'{base}/inspection/orders', params={'warning_id':wid,'inspector_name':'王巡查','district':'城东区','location':'人民路','longitude':120.15,'latitude':30.28})
requests.post(f'{base}/inspection/reports', params={'order_id':1,'water_depth':0.35,'description':'积水严重'})

print('基础数据初始化完成')

print()
print('=== 需求1: 预警时间线 ===')
r = requests.get(f'{base}/system/warnings/{wid}/timeline')
timeline = r.json()
print(f'预警ID={timeline["warning_id"]} 区域={timeline["district"]} 风险={timeline["risk_level"]}')
for node in timeline['nodes']:
    handler = node.get('handler') or '-'
    dur = f'{node["duration_minutes"]}min' if node.get('duration_minutes') else '-'
    time = node.get('occurred_at', '')[:19] if node.get('occurred_at') else '-'
    print(f'  {node["node_type"]:25s} 状态={node["status"]:18s} 处理人={handler:6s} 时间={time} 耗时={dur}')

print()
print('=== 需求2: 复盘报告 ===')
today = date.today().isoformat()
r = requests.get(f'{base}/system/incident-review', params={'warning_id': wid})
review = r.json()
print(f'降雨: {json.dumps(review.get("rainfall_summary"), ensure_ascii=False)}')
print(f'风险变化: {json.dumps(review.get("risk_level_changes"), ensure_ascii=False)}')
print(f'泵站: {json.dumps(review.get("pump_discharge_summary"), ensure_ascii=False)}')
print(f'工单: {json.dumps(review.get("work_order_summary"), ensure_ascii=False)}')
print(f'物资: {json.dumps(review.get("material_summary"), ensure_ascii=False)}')

print()
print('=== 需求3: 重复审批不再锁库 ===')
inv_before = requests.get(f'{base}/materials/inventories', params={'warehouse_id':1}).json()
locked_before = sum(i['locked_quantity'] for i in inv_before)
requests.put(f'{base}/materials/allocation-plans/{plan_id}/approve', params={'approver':'重复审批'})
inv_after = requests.get(f'{base}/materials/inventories', params={'warehouse_id':1}).json()
locked_after = sum(i['locked_quantity'] for i in inv_after)
print(f'重复审批前锁定总量: {locked_before} → 重复审批后: {locked_after}')
print(f'✅ 锁定量未增加' if locked_after == locked_before else '❌ 锁定量增加了！')

print()
print('=== 需求3: 跨区汇总只列实际参与区域 ===')
r = requests.get(f'{base}/materials/allocation-plans/{plan_id}')
plan_data = r.json()
for k, v in (plan_data.get('cross_district_summary') or {}).items():
    print(f'  {k}: 跨区{v["cross_district_quantity"]}件 来自={v["source_districts"]}')

print()
print('=== 需求4: 采购跟踪全流程 ===')
requests.post(f'{base}/materials/check-inventory')
r = requests.get(f'{base}/system/replenishment-requests')
reqs = r.json()
if reqs:
    req_id = reqs[0]['id']
    requests.put(f'{base}/materials/replenishment/{req_id}/approve-district', params={'approver':'赵区级'})
    requests.put(f'{base}/materials/replenishment/{req_id}/approve-city', params={'approver':'钱市级'})

    r = requests.get(f'{base}/system/procurements', params={'request_id': req_id})
    procs = r.json()
    print(f'采购记录: {len(procs)}条')
    if procs:
        proc_id = procs[0]['id']
        print(f'  状态={procs[0]["status"]} 数量={procs[0]["quantity"]}')

        requests.put(f'{base}/system/procurements/{proc_id}/arrive')
        r = requests.get(f'{base}/system/procurements/{proc_id}')
        print(f'  到货后: 状态={r.json()["status"]}')

        inv_before_store = requests.get(f'{base}/materials/inventories', params={'warehouse_id':reqs[0]["warehouse_id"]}).json()
        qty_before = sum(i['quantity'] for i in inv_before_store)

        requests.put(f'{base}/system/procurements/{proc_id}/store')
        r = requests.get(f'{base}/system/procurements/{proc_id}')
        print(f'  入库后: 状态={r.json()["status"]}')

        inv_after_store = requests.get(f'{base}/materials/inventories', params={'warehouse_id':reqs[0]["warehouse_id"]}).json()
        qty_after = sum(i['quantity'] for i in inv_after_store)
        print(f'  入库前库存={qty_before} → 入库后={qty_after} (增加{qty_after-qty_before})')

    r = requests.get(f'{base}/system/replenishment-requests/{req_id}')
    detail = r.json()
    print(f'补货详情: 催办{len(detail.get("reminders",[]))}条 采购{len(detail.get("procurements",[]))}条')
    for p in detail.get('procurements', []):
        print(f'  采购: 状态={p["status"]} 数量={p["quantity"]} 到货={p.get("arrived_at","-")} 入库={p.get("stored_at","-")}')

print()
print('全部验证完成!')
