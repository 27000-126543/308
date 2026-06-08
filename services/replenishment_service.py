from datetime import datetime
from sqlalchemy.orm import Session
from models import (
    MaterialInventory, Warehouse, ReplenishmentRequest,
    MaterialType, ApprovalStatus, ApprovalReminder
)
from services.push_service import push_approval, push_message


def check_inventory_levels(db: Session):
    inventories = db.query(MaterialInventory).all()
    for inv in inventories:
        available = inv.quantity - inv.locked_quantity
        if available < inv.safety_stock:
            existing = db.query(ReplenishmentRequest).filter(
                ReplenishmentRequest.warehouse_id == inv.warehouse_id,
                ReplenishmentRequest.material_type == inv.material_type,
                ReplenishmentRequest.city_approval_status != ApprovalStatus.APPROVED
            ).first()
            if not existing:
                _create_replenishment_request(db, inv)


def _create_replenishment_request(db: Session, inv: MaterialInventory):
    request_qty = inv.safety_stock * 2 - (inv.quantity - inv.locked_quantity)

    req = ReplenishmentRequest(
        warehouse_id=inv.warehouse_id,
        material_type=inv.material_type,
        current_quantity=inv.quantity - inv.locked_quantity,
        safety_stock=inv.safety_stock,
        request_quantity=max(request_qty, inv.safety_stock),
        district_approval_status=ApprovalStatus.PENDING,
        city_approval_status=ApprovalStatus.PENDING
    )
    db.add(req)
    db.flush()

    push_approval(
        db=db,
        target_role="headquarters",
        title="防汛物资补货申请-区级审批",
        content=f"仓储点{inv.warehouse_id}的{inv.material_type.value}库存{inv.quantity - inv.locked_quantity}低于安全线{inv.safety_stock}，申请补货{req.request_quantity}",
        related_id=req.id,
        related_type="replenishment"
    )

    db.commit()
    return req


def approve_district_level(db: Session, request_id: int, approver: str) -> ReplenishmentRequest:
    req = db.query(ReplenishmentRequest).filter(ReplenishmentRequest.id == request_id).first()
    if not req:
        raise ValueError("补货申请不存在")

    req.district_approval_status = ApprovalStatus.APPROVED
    req.district_approver = approver
    req.district_approved_at = datetime.utcnow()

    push_approval(
        db=db,
        target_role="headquarters",
        title="防汛物资补货申请-市级审批",
        content=f"区级已审批通过，{req.material_type.value}补货{req.request_quantity}件，请市级审批",
        related_id=req.id,
        related_type="replenishment"
    )

    db.commit()
    return req


def approve_city_level(db: Session, request_id: int, approver: str) -> ReplenishmentRequest:
    req = db.query(ReplenishmentRequest).filter(ReplenishmentRequest.id == request_id).first()
    if not req:
        raise ValueError("补货申请不存在")

    if req.district_approval_status != ApprovalStatus.APPROVED:
        raise ValueError("区级审批尚未通过")

    req.city_approval_status = ApprovalStatus.APPROVED
    req.city_approver = approver
    req.city_approved_at = datetime.utcnow()
    req.procurement_synced = True

    inv = db.query(MaterialInventory).filter(
        MaterialInventory.warehouse_id == req.warehouse_id,
        MaterialInventory.material_type == req.material_type
    ).first()
    if inv:
        inv.quantity += req.request_quantity
        inv.updated_at = datetime.utcnow()

    push_message(
        db=db,
        target_role="headquarters",
        category="approval",
        title="物资补货已完成",
        content=f"{req.material_type.value}补货{req.request_quantity}件已审批通过并同步采购",
        related_id=req.id,
        related_type="replenishment"
    )

    db.commit()
    return req


def check_approval_timeouts(db: Session):
    from datetime import timedelta
    timeout = timedelta(hours=3)

    pending_district = db.query(ReplenishmentRequest).filter(
        ReplenishmentRequest.district_approval_status == ApprovalStatus.PENDING
    ).all()

    for req in pending_district:
        elapsed = datetime.utcnow() - req.created_at
        if elapsed > timeout:
            req.district_reminder_count += 1
            reminder = ApprovalReminder(
                request_id=req.id,
                level="district",
                reminder_count=req.district_reminder_count,
                escalated=False
            )
            db.add(reminder)

            if elapsed > timeout * 2:
                req.district_approval_status = ApprovalStatus.TIMEOUT_ESCALATED
                reminder.escalated = True
                push_message(
                    db=db,
                    target_role="headquarters",
                    category="approval",
                    title="区级审批超时-已升级",
                    content=f"补货申请{req.id}区级审批超时，已自动升级至市级",
                    related_id=req.id,
                    related_type="replenishment"
                )
            else:
                push_approval(
                    db=db,
                    target_role="headquarters",
                    title="区级审批超时催办",
                    content=f"补货申请{req.id}区级审批已超时{int(elapsed.total_seconds()/3600)}小时，请尽快处理",
                    related_id=req.id,
                    related_type="replenishment"
                )

    pending_city = db.query(ReplenishmentRequest).filter(
        ReplenishmentRequest.district_approval_status == ApprovalStatus.APPROVED,
        ReplenishmentRequest.city_approval_status == ApprovalStatus.PENDING
    ).all()

    for req in pending_city:
        if not req.district_approved_at:
            continue
        elapsed = datetime.utcnow() - req.district_approved_at
        if elapsed > timeout:
            req.city_reminder_count += 1
            reminder = ApprovalReminder(
                request_id=req.id,
                level="city",
                reminder_count=req.city_reminder_count,
                escalated=False
            )
            db.add(reminder)

            push_approval(
                db=db,
                target_role="headquarters",
                title="市级审批超时催办",
                content=f"补货申请{req.id}市级审批已超时{int(elapsed.total_seconds()/3600)}小时，请尽快处理",
                related_id=req.id,
                related_type="replenishment"
            )

    db.commit()
