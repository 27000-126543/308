import requests, json
from datetime import date

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
print('=== 需求1: 处置看板 ===')
r = requests.get(f'{base}/system/warnings/{wid}/dashboard')
dash = r.json()
print(f'预警ID={dash["warning_id"]} 区域={dash["district"]} 风险={dash["risk_level"]}')
for m in dash['modules']:
    risk = '超时风险!' if m['timeout_risk'] else '正常'
    resp = m.get('responsible') or '-'
    action = m.get('next_action') or '-'
    print(f'  {m["module_name"]:20s} 状态={m["status"]:18s} 负责人={resp:10s} 下一步={action:20s} {risk}')
print(f'催办记录: {len(dash.get("urge_records",[]))}条')

print()
print('=== 需求2: 复盘报告(含考核分析+多区域分组) ===')
r = requests.get(f'{base}/system/incident-review', params={'warning_id': wid})
review = r.json()
print(f'分组数: {len(review.get("groups",[]))}')
for g in review.get('groups', []):
    print(f'  区域={g["district"]} 预警数={g["warning_count"]} 降雨={json.dumps(g.get("rainfall_summary"), ensure_ascii=False)}')
    print(f'    工单={json.dumps(g.get("work_order_summary"), ensure_ascii=False)}')
    print(f'    物资={json.dumps(g.get("material_summary"), ensure_ascii=False)}')
    print(f'    催办={json.dumps(g.get("urge_summary"), ensure_ascii=False)}')

print('考核分析:')
for p in review.get('performance', []):
    print(f'  区域={p["district"]} 平均响应={p["avg_response_minutes"]}min 超时={p["timeout_count"]} 工单完成率={p["work_order_completion_rate"]} 物资准时率={p["material_on_time_rate"]} 采购入库用时={p["avg_procurement_store_hours"]}h')
    if p.get('slowest_links'):
        for sl in p['slowest_links'][:3]:
            print(f'    最慢环节: {json.dumps(sl, ensure_ascii=False)}')

print()
print('=== 需求3: 时间线待处理节点完整显示 ===')
r = requests.get(f'{base}/system/warnings/{wid}/timeline')
timeline = r.json()
pending_count = 0
for node in timeline['nodes']:
    if node['status'] == 'pending':
        pending_count += 1
        print(f'  待处理: {node["node_type"]}')
all_types = [n['node_type'] for n in timeline['nodes']]
expected = ['warning_triggered','pump_dispatch','resource_plan_created','resource_plan_approved',
            'material_shipped','material_arrived','material_consumed',
            'inspection_assigned','inspection_reported','traffic_control']
missing = [t for t in expected if t not in all_types]
print(f'时间线节点类型: {all_types}')
print(f'缺失节点: {missing if missing else "无-全部覆盖"}')
print(f'待处理节点数: {pending_count}')

print()
print('=== 需求3: 日报消耗按实际日期统计 ===')
requests.post(f'{base}/system/generate-daily-report', params={'report_date': date.today().isoformat()})
r = requests.get(f'{base}/system/daily-reports', params={'district': '城东区'})
if r.json():
    rpt = r.json()[0]
    print(f'出库={rpt.get("material_shipped")} 到达={rpt.get("material_arrived")} 消耗={rpt.get("material_consumption")}')

print()
print('=== 需求4: 协同催办 ===')
r = requests.post(f'{base}/system/urges', json={
    'target_type': 'warehouse_ship',
    'target_id': aid if allocs else 1,
    'warning_id': wid,
    'urger': '值班员张三',
    'remark': '出库超时请尽快处理'
})
print(f'首次催办: ID={r.json()["id"]} 次数={r.json()["urge_count"]}')

r = requests.post(f'{base}/system/urges', json={
    'target_type': 'warehouse_ship',
    'target_id': aid if allocs else 1,
    'warning_id': wid,
    'urger': '值班员张三',
    'remark': '再次催办-紧急'
})
print(f'重复催办: ID={r.json()["id"]} 次数={r.json()["urge_count"]}')

r = requests.post(f'{base}/system/urges', json={
    'target_type': 'pump_confirm',
    'target_id': 1,
    'warning_id': wid,
    'urger': '值班员李四',
    'remark': '泵站确认超时'
})
print(f'泵站催办: ID={r.json()["id"]} 次数={r.json()["urge_count"]}')

r = requests.get(f'{base}/system/urges', params={'warning_id': wid})
print(f'预警{wid}催办记录: {len(r.json())}条')

r = requests.get(f'{base}/system/warnings/{wid}/dashboard')
dash = r.json()
print(f'看板催办记录: {len(dash.get("urge_records",[]))}条')
for u in dash.get('urge_records', []):
    print(f'  类型={u["target_type"]} 目标ID={u["target_id"]} 次数={u["urge_count"]} 最近={u["last_urged_at"][:19]}')

r = requests.get(f'{base}/system/incident-review', params={'warning_id': wid})
review = r.json()
for g in review.get('groups', []):
    us = g.get('urge_summary', {})
    print(f'复盘-区域{g["district"]}催办汇总: {json.dumps(us, ensure_ascii=False)}')

print()
print('=== 全部测试完成 ===')
