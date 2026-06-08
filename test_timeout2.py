import requests
from datetime import datetime, timedelta

base = 'http://localhost:8000/api'

try:
    from database import SessionLocal
    from models import ReplenishmentRequest, Warehouse

    db = SessionLocal()
    wh = Warehouse(name='test', district='城东区', longitude=120.1, latitude=30.2)
    db.add(wh)
    db.commit()
    wh_id = wh.id

    req = ReplenishmentRequest(
        warehouse_id=wh_id, material_type='water_pump',
        current_quantity=5, safety_stock=20, request_quantity=35,
        district_approval_status='pending', city_approval_status='pending',
        created_at=datetime.utcnow() - timedelta(hours=4)
    )
    db.add(req)
    db.commit()
    req_id = req.id
    db.close()
    print(f'创建申请{req_id}，created_at=4h前')

    r = requests.post(f'{base}/system/check-approval-timeouts')
    print(f'超时检查: {r.json()}')

    r = requests.get(f'{base}/system/replenishment-requests')
    for rq in r.json():
        if rq['id'] == req_id:
            print(f'区级={rq["district_approval_status"]} 市级={rq["city_approval_status"]}')
            print(f'区级催办={rq["district_reminder_count"]} 市级催办={rq["city_reminder_count"]}')

    r = requests.get(f'{base}/system/approval-reminders', params={'request_id': req_id})
    print(f'催办记录: {len(r.json())}条')
    for rm in r.json():
        print(f'  级别={rm["level"]} 升级={rm["escalated"]} 内容={rm["content"]}')

    db = SessionLocal()
    req = db.query(ReplenishmentRequest).filter(ReplenishmentRequest.id == req_id).first()
    print(f'district_approved_at={req.district_approved_at}')
    req.district_approved_at = datetime.utcnow() - timedelta(hours=4)
    db.commit()
    db.close()
    print('设district_approved_at为4h前')

    r = requests.post(f'{base}/system/check-approval-timeouts')
    r = requests.get(f'{base}/system/replenishment-requests')
    for rq in r.json():
        if rq['id'] == req_id:
            print(f'市级={rq["city_approval_status"]} 市级催办={rq["city_reminder_count"]}')

    r = requests.get(f'{base}/system/approval-reminders', params={'request_id': req_id})
    print(f'总催办记录: {len(r.json())}条')
    for rm in r.json():
        print(f'  级别={rm["level"]} 升级={rm["escalated"]} 内容={rm["content"]}')

except Exception as e:
    import traceback
    traceback.print_exc()
