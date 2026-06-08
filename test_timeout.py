import requests
from datetime import datetime, timedelta

base = 'http://localhost:8000/api'

print('=== 补货超时分层计时验证 ===')
from database import SessionLocal
from models import ReplenishmentRequest

db = SessionLocal()

print('第1步: 创建补货申请，created_at为4小时前')
req = ReplenishmentRequest(
    warehouse_id=1, material_type='water_pump',
    current_quantity=5, safety_stock=20, request_quantity=35,
    district_approval_status='pending', city_approval_status='pending',
    created_at=datetime.utcnow() - timedelta(hours=4)
)
db.add(req)

from models import Warehouse, MaterialInventory
wh = Warehouse(name='test', district='城东区', longitude=120.1, latitude=30.2)
db.add(wh)
db.commit()
req_id = req.id
wh_id = wh.id
req.warehouse_id = wh_id
db.commit()
db.close()

print('第2步: 第一次超时检查 → 区级应升级，市级不应升级')
requests.post(f'{base}/system/check-approval-timeouts')
r = requests.get(f'{base}/system/replenishment-requests')
for rq in r.json():
    if rq['id'] == req_id:
        print(f'  区级={rq["district_approval_status"]} 市级={rq["city_approval_status"]}')
        print(f'  区级催办={rq["district_reminder_count"]} 市级催办={rq["city_reminder_count"]}')
        assert rq['district_approval_status'] == 'timeout_escalated', '区级应该timeout_escalated'
        assert rq['city_approval_status'] == 'pending', '市级应该还是pending'
        print('  ✅ 区级已升级，市级未升级')

r = requests.get(f'{base}/system/approval-reminders', params={'request_id': req_id})
for rm in r.json():
    print(f'  催办: 级别={rm["level"]} 已升级={rm["escalated"]} 内容={rm["content"]}')

print('第3步: district_approved_at设为4小时前(模拟市级已等4h) → 第二次检查市级应升级')
db = SessionLocal()
req = db.query(ReplenishmentRequest).filter(ReplenishmentRequest.id == req_id).first()
req.district_approved_at = datetime.utcnow() - timedelta(hours=4)
db.commit()
db.close()

requests.post(f'{base}/system/check-approval-timeouts')
r = requests.get(f'{base}/system/replenishment-requests')
for rq in r.json():
    if rq['id'] == req_id:
        print(f'  区级={rq["district_approval_status"]} 市级={rq["city_approval_status"]}')
        print(f'  区级催办={rq["district_reminder_count"]} 市级催办={rq["city_reminder_count"]}')
        assert rq['city_approval_status'] == 'timeout_escalated', '市级应该timeout_escalated'
        print('  ✅ 市级也已升级')

r = requests.get(f'{base}/system/approval-reminders', params={'request_id': req_id})
for rm in r.json():
    print(f'  催办: 级别={rm["level"]} 已升级={rm["escalated"]} 内容={rm["content"]}')

print()
print('✅ 补货审批超时分层计时验证通过!')
