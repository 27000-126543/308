import requests
import json
from datetime import datetime, timedelta

base = 'http://localhost:8000/api'

print('=== 修复3验证: 补货审批超时 ===')
from database import SessionLocal
from models import ReplenishmentRequest, ApprovalReminder
from services.replenishment_service import check_approval_timeouts

db = SessionLocal()
req = ReplenishmentRequest(
    warehouse_id=1,
    material_type='assault_boat',
    current_quantity=3,
    safety_stock=10,
    request_quantity=17,
    district_approval_status='pending',
    city_approval_status='pending',
    created_at=datetime.utcnow() - timedelta(hours=4)
)
db.add(req)
db.commit()
req_id = req.id
print(f'创建补货申请{req_id}，创建时间为4小时前')

check_approval_timeouts(db)

req = db.query(ReplenishmentRequest).filter(ReplenishmentRequest.id == req_id).first()
print(f'区级状态: {req.district_approval_status}')
print(f'区级催办次数: {req.district_reminder_count}')

reminders = db.query(ApprovalReminder).filter(ApprovalReminder.request_id == req_id).all()
print(f'催办记录: {len(reminders)}条')
for r in reminders:
    print(f'  级别={r.level} 已升级={r.escalated} 催办次数={r.reminder_count}')

msgs = requests.get(f'{base}/messages', params={'target_role':'headquarters','category':'approval','limit':5}).json()
for m in msgs:
    if '超时' in m['title']:
        print(f'  消息: [{m["title"]}] {m["content"]}')

print()
print('=== 市级超时验证 ===')
req.district_approval_status = 'approved'
req.district_approver = '赵区级'
req.district_approved_at = datetime.utcnow() - timedelta(hours=4)
db.commit()

check_approval_timeouts(db)

req = db.query(ReplenishmentRequest).filter(ReplenishmentRequest.id == req_id).first()
print(f'市级状态: {req.city_approval_status}')
print(f'市级催办次数: {req.city_reminder_count}')

reminders = db.query(ApprovalReminder).filter(ApprovalReminder.request_id == req_id).all()
for r in reminders:
    print(f'  级别={r.level} 已升级={r.escalated} 催办次数={r.reminder_count}')

msgs = requests.get(f'{base}/messages', params={'target_role':'headquarters','category':'approval','limit':10}).json()
for m in msgs:
    if '超时' in m['title'] or '升级' in m['title']:
        print(f'  消息: [{m["title"]}] {m["content"]}')

db.close()

print()
print('=== 修复4验证: 日报物资消耗按日期+片区 ===')
db = SessionLocal()
from models import ResourceAllocationPlan
plan = db.query(ResourceAllocationPlan).first()
if plan:
    plan.approved_at = datetime.utcnow()
    db.commit()
    print(f'将调配方案{plan.id}审批时间设为今天')

from services.report_service import generate_daily_report
today = datetime.utcnow().date()
generate_daily_report(db, today)

from models import DailyReport
reports = db.query(DailyReport).filter(DailyReport.report_date == today).all()
for rp in reports:
    print(f'  日期={rp.report_date} 区域={rp.district} 物资消耗={rp.material_consumption}')

db.close()

print()
print('全部修复验证完成!')
