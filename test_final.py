import requests, json, traceback
from datetime import date

base = 'http://localhost:8000/api'
results = []

def log(s):
    results.append(s)
    try:
        print(s)
    except:
        pass

try:
    requests.post(f'{base}/stations/rain', json={'name':'城东雨量站','code':'RAIN001','district':'城东区','longitude':120.15,'latitude':30.28,'elevation':4.5})
    requests.post(f'{base}/pump/stations', json={'name':'城东泵站','code':'PUMP001','district':'城东区','longitude':120.15,'latitude':30.28,'design_capacity':500,'status':'stopped'})
    requests.post(f'{base}/materials/warehouses', json={'name':'城东仓储点A','district':'城东区','longitude':120.17,'latitude':30.30})
    requests.post(f'{base}/materials/warehouses', json={'name':'城西仓储点','district':'城西区','longitude':120.05,'latitude':30.25})
    for w_id in [1, 2]:
        for mt in ['water_pump', 'sandbag', 'assault_boat']:
            qty = 10 if mt == 'water_pump' else (200 if mt == 'sandbag' else 2)
            safe = 20 if mt == 'water_pump' else (500 if mt == 'sandbag' else 10)
            requests.post(f'{base}/materials/inventories', json={'warehouse_id':w_id,'material_type':mt,'quantity':qty,'safety_stock':safe,'locked_quantity':0})

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
    aid = allocs[0]['id'] if allocs else None
    if aid:
        requests.put(f'{base}/materials/allocations/{aid}/ship')
        requests.put(f'{base}/materials/allocations/{aid}/arrive', params={'receiver':'李现场'})
        requests.put(f'{base}/materials/allocations/{aid}/consume', params={'consumed_quantity':5})

    requests.post(f'{base}/inspection/orders', params={'warning_id':wid,'inspector_name':'王巡查','district':'城东区','location':'人民路','longitude':120.15,'latitude':30.28})
    requests.post(f'{base}/inspection/reports', params={'order_id':1,'water_depth':0.35,'description':'积水严重'})

    log('=== 催办验证 ===')
    r = requests.post(f'{base}/system/urges', json={
        'target_type': 'warehouse_ship', 'target_id': aid or 1,
        'warning_id': wid, 'urger': '张三', 'remark': '首次'
    })
    u1 = r.json()
    log(f'首次催办: ID={u1["id"]} 次数={u1["urge_count"]}')
    if u1['urge_count'] != 1:
        log(f'  WARN: 首次应为1, 实际{u1["urge_count"]}')

    r = requests.post(f'{base}/system/urges', json={
        'target_type': 'warehouse_ship', 'target_id': aid or 1,
        'warning_id': wid, 'urger': '张三', 'remark': '再次'
    })
    u2 = r.json()
    log(f'重复催办: ID={u2["id"]} 次数={u2["urge_count"]}')
    if u2['urge_count'] != 2:
        log(f'  WARN: 重复应为2, 实际{u2["urge_count"]}')

    log('=== 看板验证 ===')
    r = requests.get(f'{base}/system/warnings/{wid}/dashboard')
    if r.status_code != 200:
        log(f'看板ERROR: {r.status_code} {r.text[:300]}')
    else:
        dash = r.json()
        module_names = [m['module_name'] for m in dash['modules']]
        log(f'看板模块: {module_names}')
        for m in dash['modules']:
            log(f'  {m["module_name"]:20s} 状态={m["status"]:18s} 超时={m["timeout_risk"]}')
        log(f'催办记录: {len(dash.get("urge_records",[]))}条')

    log('=== 时间线验证 ===')
    r = requests.get(f'{base}/system/warnings/{wid}/timeline')
    timeline = r.json()
    all_types = [n['node_type'] for n in timeline['nodes']]
    expected = ['warning_triggered','pump_dispatch','resource_plan_created','resource_plan_approved',
                'material_shipped','material_arrived','material_consumed',
                'inspection_assigned','inspection_reported','traffic_control']
    missing = [t for t in expected if t not in all_types]
    log(f'节点: {all_types}')
    log(f'缺失: {missing if missing else "无"}')
    pending = [n for n in timeline['nodes'] if n['status'] == 'pending']
    log(f'待处理: {[n["node_type"] for n in pending]}')

    log('=== 复盘报告验证 ===')
    r = requests.get(f'{base}/system/incident-review', params={'warning_id': wid})
    if r.status_code != 200:
        log(f'复盘ERROR: {r.status_code} {r.text[:300]}')
    else:
        review = r.json()
        log(f'groups字段: {"有" if "groups" in review else "无"}')
        log(f'performance字段: {"有" if "performance" in review else "无"}')
        for g in review.get('groups', []):
            log(f'  区域={g["district"]} 预警数={g["warning_count"]}')
        for pf in review.get('performance', []):
            log(f'  绩效: 区域={pf["district"]} 工单完成率={pf["work_order_completion_rate"]} 超时={pf["timeout_count"]}')

    log('=== 日报验证 ===')
    requests.post(f'{base}/system/generate-daily-report', params={'report_date': date.today().isoformat()})
    r = requests.get(f'{base}/system/daily-reports', params={'district': '城东区'})
    if r.json():
        rpt = r.json()[0]
        log(f'出库={rpt.get("material_shipped")} 到达={rpt.get("material_arrived")} 消耗={rpt.get("material_consumption")}')

    log('=== ALL DONE ===')
except Exception as e:
    log(f'ERROR: {e}')
    log(traceback.format_exc())

with open('d:/新项目/308/r.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
