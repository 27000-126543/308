import requests
import json
from datetime import datetime, timedelta, date

base = 'http://localhost:8000/api'

print('=== 初始化基础数据 ===')
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
print('基础数据初始化完成')

print()
print('=== 需求1: 物资调配全流程(锁定→出库→到达→消耗) ===')
requests.post(f'{base}/stations/rain-data', json={'station_id':1,'rainfall_1h':50,'rainfall_3h':100,'rainfall_6h':150,'rainfall_24h':200})
r = requests.get(f'{base}/warnings')
wid = r.json()[0]['id']
r = requests.post(f'{base}/warnings/{wid}/trigger-resource-plan')
plan_id = r.json().get('plan_id')

r = requests.put(f'{base}/materials/allocation-plans/{plan_id}/approve', params={'approver':'张指挥长'})
print(f'方案审批: {r.status_code}')

r = requests.get(f'{base}/materials/allocations', params={'plan_id': plan_id})
allocs = r.json()
print(f'调配明细数量: {len(allocs)}')
for a in allocs[:3]:
    print(f'  仓库{a["warehouse_id"]} {a["material_type"]} {a["quantity"]}件 距离{a["distance_km"]}km 跨区={a["is_cross_district"]} 预计到达{a["estimated_arrival_hours"]}h 状态={a["status"]}')

if allocs:
    aid = allocs[0]['id']
    r = requests.put(f'{base}/materials/allocations/{aid}/ship')
    print(f'出库: {r.status_code} 状态={r.json().get("status")} shipped_at={r.json().get("shipped_at")}')

    r = requests.put(f'{base}/materials/allocations/{aid}/arrive', params={'receiver':'李现场'})
    print(f'签收: {r.status_code} 状态={r.json().get("status")} receiver={r.json().get("receiver")}')

    r = requests.put(f'{base}/materials/allocations/{aid}/consume', params={'consumed_quantity':5})
    print(f'消耗5件: {r.status_code} consumed_quantity={r.json().get("consumed_quantity")} 状态={r.json().get("status")}')

r = requests.get(f'{base}/materials/inventories', params={'warehouse_id': 1})
inv = r.json()
for i in inv:
    print(f'  仓库1 {i["material_type"]} 总量={i["quantity"]} 锁定={i["locked_quantity"]}')

print()
print('=== 需求2: 补货审批超时分层计时 ===')
db = SessionLocal()
from models import ReplenishmentRequest
req = ReplenishmentRequest(
    warehouse_id=1, material_type='water_pump',
    current_quantity=5, safety_stock=20,
    request_quantity=35,
    district_approval_status='pending',
    city_approval_status='pending',
    created_at=datetime.utcnow() - timedelta(hours=4)
)
db.add(req)
db.commit()
req_id = req.id
db.close()
print(f'创建补货申请{req_id}，created_at为4小时前')

requests.post(f'{base}/system/check-approval-timeouts')
r = requests.get(f'{base}/system/replenishment-requests')
for rq in r.json():
    if rq['id'] == req_id:
        print(f'  区级={rq["district_approval_status"]} 市级={rq["city_approval_status"]} 区级催办={rq["district_reminder_count"]} 市级催办={rq["city_reminder_count"]}')

r = requests.get(f'{base}/system/approval-reminders', params={'request_id': req_id})
reminders = r.json()
print(f'催办记录: {len(reminders)}条')
for rm in reminders:
    print(f'  级别={rm["level"]} 已升级={rm["escalated"]} 内容={rm["content"]}')

db = SessionLocal()
req = db.query(ReplenishmentRequest).filter(ReplenishmentRequest.id == req_id).first()
req.district_approved_at = datetime.utcnow() - timedelta(hours=4)
db.commit()
db.close()

requests.post(f'{base}/system/check-approval-timeouts')
r = requests.get(f'{base}/system/approval-reminders', params={'request_id': req_id})
reminders = r.json()
print(f'市级超时后催办记录: {len(reminders)}条')
for rm in reminders:
    print(f'  级别={rm["level"]} 已升级={rm["escalated"]} 内容={rm["content"]}')

print()
print('=== 需求3: 催办记录查询API ===')
r = requests.get(f'{base}/system/approval-reminders', params={'level': 'district'})
print(f'区级催办: {len(r.json())}条')
r = requests.get(f'{base}/system/approval-reminders', params={'escalated': True})
print(f'已升级: {len(r.json())}条')
r = requests.get(f'{base}/system/approval-reminders', params={'request_id': req_id, 'level': 'city'})
print(f'指定申请+市级: {len(r.json())}条')

print()
print('=== 需求4: 跨区支援 ===')
r = requests.get(f'{base}/materials/allocation-plans/{plan_id}')
plan_detail = r.json()
print(f'方案plan_data:')
for k, v in plan_detail['plan_data'].items():
    print(f'  {k}: 需求={v["needed"]} 本区={v["local_allocated"]} 跨区={v["cross_district_allocated"]} 缺口={v["shortage"]}')
print(f'跨区汇总:')
for k, v in (plan_detail.get('cross_district_summary') or {}).items():
    print(f'  {k}: 跨区数量={v["cross_district_quantity"]} 来源区={v["source_districts"]}')

r = requests.get(f'{base}/materials/allocations', params={'plan_id': plan_id, 'is_cross_district': True})
cross_allocs = r.json()
print(f'跨区调配明细: {len(cross_allocs)}条')
for a in cross_allocs:
    print(f'  仓库{a["warehouse_id"]} {a["material_type"]} {a["quantity"]}件 距离{a["distance_km"]}km 预计{a["estimated_arrival_hours"]}h')

print()
print('=== 需求5: 日报按日期范围+区域导出 ===')
db = SessionLocal()
from models import ResourceAllocationPlan
plan = db.query(ResourceAllocationPlan).filter(ResourceAllocationPlan.id == plan_id).first()
plan.approved_at = datetime.utcnow()
db.commit()
db.close()

today = date.today().isoformat()
requests.post(f'{base}/system/generate-daily-report', params={'report_date': today})
r = requests.get(f'{base}/system/daily-reports', params={'start_date': today, 'end_date': today})
reports = r.json()
for rp in reports:
    print(f'  {rp["report_date"]} {rp["district"]}')
    print(f'    消耗: {rp["material_consumption"]}')
    print(f'    出库: {rp["material_shipped"]}')
    print(f'    到达: {rp["material_arrived"]}')

print()
print('全部5个需求验证完成!')
