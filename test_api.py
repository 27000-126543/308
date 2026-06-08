import requests
import json

base = 'http://localhost:8000/api'

print('=== 1. 初始化基础数据 ===')
r = requests.post(f'{base}/stations/rain', json={'name':'城东雨量站','code':'RAIN001','district':'城东区','longitude':120.15,'latitude':30.28,'elevation':4.5})
print(f'雨量站: {r.status_code}')

r = requests.post(f'{base}/stations/water-level', json={'name':'城东水位站','code':'WL001','district':'城东区','longitude':120.16,'latitude':30.29,'warning_level':3.5,'guarantee_level':4.5})
print(f'水位站: {r.status_code}')

r = requests.post(f'{base}/pump/stations', json={'name':'城东泵站','code':'PUMP001','district':'城东区','longitude':120.15,'latitude':30.28,'design_capacity':500,'status':'stopped'})
print(f'泵站: {r.status_code}')

r = requests.post(f'{base}/pump/devices', json={'station_id':1,'name':'1号水泵','model':'WQ-500','rated_power':110,'running_hours':2100,'maintenance_cycle_hours':2000,'status':'running'})
print(f'设备: {r.status_code}')

r = requests.post(f'{base}/materials/warehouses', json={'name':'城东仓储点','district':'城东区','longitude':120.17,'latitude':30.30})
print(f'仓库: {r.status_code}')

r = requests.post(f'{base}/materials/inventories', json={'warehouse_id':1,'material_type':'water_pump','quantity':50,'safety_stock':20,'locked_quantity':0})
r = requests.post(f'{base}/materials/inventories', json={'warehouse_id':1,'material_type':'sandbag','quantity':800,'safety_stock':500,'locked_quantity':0})
r = requests.post(f'{base}/materials/inventories', json={'warehouse_id':1,'material_type':'assault_boat','quantity':3,'safety_stock':10,'locked_quantity':0})
print('库存: 全部创建')

r = requests.post(f'{base}/maintenance/teams', json={'name':'东区电气班组','skills':'电气维修,机械维修,高压操作','district':'城东区','longitude':120.16,'latitude':30.29,'available':True})
print(f'维修班组: {r.status_code}')

from database import SessionLocal
from models import PipeNetwork, GroundElevation
db = SessionLocal()
db.add(PipeNetwork(district='城东区', total_capacity=10000, current_usage=7500))
db.add(GroundElevation(district='城东区', area_name='低洼片区', longitude=120.15, latitude=30.28, elevation=3.5, drainage_grade='P1'))
db.commit()
db.close()
print('管网+高程: ok')

print()
print('=== 2. 上传暴雨数据 → 触发预警+泵站预排 ===')
r = requests.post(f'{base}/stations/rain-data', json={'station_id':1,'rainfall_1h':50,'rainfall_3h':100,'rainfall_6h':150,'rainfall_24h':200})
print(f'降雨数据: {r.status_code}')
r = requests.get(f'{base}/warnings')
warnings = r.json()
print(f'预警: {json.dumps(warnings, ensure_ascii=False)}')
r = requests.get(f'{base}/pump/dispatches')
print(f'泵站调度: {json.dumps(r.json(), ensure_ascii=False)}')

print()
print('=== 3. 橙色/红色预警 → 资源调配方案 → 审批 → 锁定库存 ===')
wid = warnings[0]['id']
r = requests.post(f'{base}/warnings/{wid}/trigger-resource-plan')
print(f'触发调配: {r.json()}')
r = requests.get(f'{base}/materials/allocation-plans')
plans = r.json()
print(f'调配方案: {json.dumps(plans, ensure_ascii=False)}')
if plans:
    plan_id = plans[0]['id']
    r = requests.put(f'{base}/materials/allocation-plans/{plan_id}/approve', params={'approver':'张指挥长'})
    print(f'审批通过: {r.status_code}')
    r = requests.get(f'{base}/materials/inventories')
    inventories = r.json()
    for inv in inventories:
        print(f'  {inv["material_type"]}: 总量={inv["quantity"]}, 锁定={inv["locked_quantity"]}')

print()
print('=== 4. 巡查上报 → 交通管制 ===')
r = requests.post(f'{base}/inspection/orders', params={'warning_id':wid,'inspector_name':'李巡查','district':'城东区','location':'人民路','longitude':120.15,'latitude':30.28})
order_data = r.json()
print(f'创建巡查工单: {r.status_code}, id={order_data.get("id")}')
order_id = order_data.get('id', 1)

r = requests.post(f'{base}/inspection/reports', params={'order_id':order_id,'water_depth':0.35,'description':'路面积水严重'})
report_data = r.json()
print(f'巡查上报: {r.status_code}, needs_traffic_control={report_data.get("needs_traffic_control")}')

r = requests.get(f'{base}/inspection/traffic-plans')
tc_plans = r.json()
print(f'交通管制方案数量: {len(tc_plans)}')
if tc_plans:
    tc_id = tc_plans[0]['id']
    r = requests.put(f'{base}/inspection/traffic-plans/{tc_id}/approve', params={'approver':'王交警'})
    print(f'交警审批: {r.status_code}, screen_updated={r.json().get("screen_updated")}')

print()
print('=== 5. 维保工单 ===')
r = requests.post(f'{base}/maintenance/check-cycles')
print(f'维保检查: {r.json()}')
r = requests.get(f'{base}/maintenance/orders')
m_orders = r.json()
print(f'维保工单数量: {len(m_orders)}')
if m_orders:
    m_id = m_orders[0]['id']
    r = requests.put(f'{base}/maintenance/orders/{m_id}/complete')
    print(f'完成维保: {r.status_code}')

print()
print('=== 6. 物资补货 ===')
r = requests.post(f'{base}/materials/check-inventory')
r = requests.get(f'{base}/system/replenishment-requests')
reqs = r.json()
print(f'补货申请数量: {len(reqs)}')
if reqs:
    req_id = reqs[0]['id']
    r = requests.put(f'{base}/materials/replenishment/{req_id}/approve-district', params={'approver':'赵区级'})
    print(f'区级审批: {r.json()}')
    r = requests.put(f'{base}/materials/replenishment/{req_id}/approve-city', params={'approver':'钱市级'})
    print(f'市级审批: {r.json()}')

print()
print('=== 7. 日报生成 ===')
r = requests.post(f'{base}/system/generate-daily-report')
print(f'生成日报: {r.json()}')
r = requests.get(f'{base}/system/daily-reports')
print(f'日报数量: {len(r.json())}')

print()
print('=== 8. 消息推送汇总 ===')
for role in ['headquarters','inspector','pump_duty','traffic_dept','planning_dept','maintenance_team']:
    r = requests.get(f'{base}/messages', params={'target_role':role,'limit':10})
    msgs = r.json()
    if msgs:
        print(f'{role}: {len(msgs)}条')
        for m in msgs[:3]:
            print(f'  [{m["category"]}] {m["title"]}')

print()
print('=== 仪表盘 ===')
r = requests.get('http://localhost:8000/api/dashboard/summary')
print(json.dumps(r.json(), ensure_ascii=False))
