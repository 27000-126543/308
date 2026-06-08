import requests
import json
from datetime import datetime, timedelta

base = 'http://localhost:8000/api'

print('=== 初始化基础数据 ===')
requests.post(f'{base}/stations/rain', json={'name':'城东雨量站','code':'RAIN001','district':'城东区','longitude':120.15,'latitude':30.28,'elevation':4.5})
requests.post(f'{base}/stations/water-level', json={'name':'城东水位站','code':'WL001','district':'城东区','longitude':120.16,'latitude':30.29,'warning_level':3.5,'guarantee_level':4.5})
requests.post(f'{base}/pump/stations', json={'name':'城东泵站','code':'PUMP001','district':'城东区','longitude':120.15,'latitude':30.28,'design_capacity':500,'status':'stopped'})
requests.post(f'{base}/pump/devices', json={'station_id':1,'name':'1号水泵','model':'WQ-500','rated_power':110,'running_hours':2100,'maintenance_cycle_hours':2000,'status':'running'})

requests.post(f'{base}/materials/warehouses', json={'name':'城东仓储点A','district':'城东区','longitude':120.17,'latitude':30.30})
requests.post(f'{base}/materials/warehouses', json={'name':'城东仓储点B','district':'城东区','longitude':120.19,'latitude':30.31})
requests.post(f'{base}/materials/warehouses', json={'name':'城西仓储点','district':'城西区','longitude':120.05,'latitude':30.25})

for wid in [1, 2, 3]:
    for mt in ['water_pump', 'sandbag', 'assault_boat']:
        qty = 50 if mt == 'water_pump' else (1000 if mt == 'sandbag' else 15)
        safe = 20 if mt == 'water_pump' else (500 if mt == 'sandbag' else 10)
        requests.post(f'{base}/materials/inventories', json={'warehouse_id':wid,'material_type':mt,'quantity':qty,'safety_stock':safe,'locked_quantity':0})

requests.post(f'{base}/maintenance/teams', json={'name':'东区电气班组','skills':'电气维修,机械维修,高压操作','district':'城东区','longitude':120.16,'latitude':30.29,'available':True})

from database import SessionLocal
from models import PipeNetwork, GroundElevation
db = SessionLocal()
db.add(PipeNetwork(district='城东区', total_capacity=10000, current_usage=7500))
db.add(GroundElevation(district='城东区', area_name='低洼片区', longitude=120.15, latitude=30.28, elevation=3.5, drainage_grade='P1'))
db.commit()
db.close()
print('基础数据初始化完成')

print()
print('=== 修复1: 资源调配距离 ===')
requests.post(f'{base}/stations/rain-data', json={'station_id':1,'rainfall_1h':50,'rainfall_3h':100,'rainfall_6h':150,'rainfall_24h':200})
r = requests.get(f'{base}/warnings')
wid = r.json()[0]['id']
r = requests.post(f'{base}/warnings/{wid}/trigger-resource-plan')
print(f'触发调配: {r.json()}')
r = requests.get(f'{base}/materials/allocation-plans')
plans = r.json()
if plans:
    plan_id = plans[0]['id']
    r = requests.get(f'{base}/materials/allocations', params={'plan_id': plan_id})
    allocs = r.json()
    print('调配明细(距离):')
    for a in allocs:
        print(f'  仓库{a["warehouse_id"]} {a["material_type"]} {a["quantity"]}件 距离{a["distance_km"]}km')

print()
print('=== 修复2: 高风险隐患(需3次积水) ===')
from database import SessionLocal as SL
from models import WaterloggingEvent
db = SL()
for i in range(3):
    from services.risk_service import record_waterlogging_event
    record_waterlogging_event(db, '人民路口', '城东区', 120.151, 30.281, 0.2 + i * 0.1)
db.close()

r = requests.get(f'{base}/system/hidden-dangers')
dangers = r.json()
print(f'隐患点数量: {len(dangers)}')
for d in dangers:
    print(f'  {d["location"]} 积水{d["waterlogging_count"]}次 高风险={d["is_high_risk"]} 建议={d["renovation_suggestion"][:30]}... 已推送={d["pushed_to_planning"]} 纳入年度计划={d["in_annual_plan"]}')

print()
print('=== 修复3: 补货审批超时3小时 ===')
requests.post(f'{base}/materials/check-inventory')
r = requests.get(f'{base}/system/replenishment-requests')
reqs = r.json()
print(f'补货申请数量: {len(reqs)}')

if reqs:
    req_id = reqs[0]['id']
    db = SL()
    from models import ReplenishmentRequest
    from datetime import datetime, timedelta
    req_obj = db.query(ReplenishmentRequest).filter(ReplenishmentRequest.id == req_id).first()
    req_obj.created_at = datetime.utcnow() - timedelta(hours=4)
    db.commit()
    db.close()
    print(f'已将申请{req_id}创建时间改为4小时前')

    requests.post(f'{base}/system/check-approval-timeouts')
    r = requests.get(f'{base}/system/replenishment-requests')
    reqs = r.json()
    for req in reqs:
        print(f'  申请{req["id"]}: 区级={req["district_approval_status"]} 市级={req["city_approval_status"]} 区级催办={req["district_reminder_count"]}')

    from models import ApprovalReminder
    db = SL()
    reminders = db.query(ApprovalReminder).all()
    print(f'催办记录数量: {len(reminders)}')
    for rm in reminders:
        print(f'  申请{rm.request_id} 级别={rm.level} 催办次数={rm.reminder_count} 已升级={rm.escalated}')
    db.close()

print()
print('=== 修复4: 日报物资消耗按日期+片区 ===')
if plans:
    r = requests.put(f'{base}/materials/allocation-plans/{plans[0]["id"]}/approve', params={'approver':'张指挥长'})
    print(f'审批调配方案: {r.status_code}')

r = requests.post(f'{base}/system/generate-daily-report')
print(f'生成日报: {r.json()}')
r = requests.get(f'{base}/system/daily-reports')
reports = r.json()
for rp in reports:
    print(f'  日期={rp["report_date"]} 区域={rp["district"]} 物资消耗={rp["material_consumption"]}')

print()
print('全部修复验证完成!')
