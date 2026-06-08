from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models import (
    MaterialInventory, Warehouse, ReplenishmentRequest,
    MaterialType, ApprovalStatus, ApprovalReminder,
    ProcurementRecord, ProcurementStatus
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

    if req.district_approval_status not in (ApprovalStatus.APPROVED, ApprovalStatus.TIMEOUT_ESCALATED):
        raise ValueError("区级审批尚未通过")

    req.city_approval_status = ApprovalStatus.APPROVED
    req.city_approver = approver
    req.city_approved_at = datetime.utcnow()
    req.procurement_synced = True

    procurement = ProcurementRecord(
        request_id=req.id,
        status=ProcurementStatus.PURCHASING,
        quantity=req.request_quantity,
        purchasing_at=datetime.utcnow()
    )
    db.add(procurement)

    push_message(
        db=db,
        target_role="headquarters",
        category="approval",
        title="物资补货已审批-采购中",
        content=f"{req.material_type.value}补货{req.request_quantity}件已审批通过，已创建采购记录",
        related_id=req.id,
        related_type="replenishment"
    )

    db.commit()
    return req


def check_approval_timeouts(db: Session):
    timeout = timedelta(hours=3)

    _check_district_timeouts(db, timeout)
    _check_city_timeouts(db, timeout)

    db.commit()


def _check_district_timeouts(db: Session, timeout: timedelta):
    pending_district = db.query(ReplenishmentRequest).filter(
        ReplenishmentRequest.district_approval_status == ApprovalStatus.PENDING
    ).all()

    for req in pending_district:
        elapsed = datetime.utcnow() - req.created_at
        if elapsed > timeout:
            req.district_approval_status = ApprovalStatus.TIMEOUT_ESCALATED
            req.district_approved_at = datetime.utcnow()
            req.district_reminder_count += 1
            hours = int(elapsed.total_seconds() / 3600)

            content = f"补货申请{req.id}区级审批已超时{hours}小时，自动转交市级审批"
            reminder = ApprovalReminder(
                request_id=req.id,
                level="district",
                reminder_count=req.district_reminder_count,
                escalated=True,
                content=content
            )
            db.add(reminder)

            push_message(
                db=db,
                target_role="headquarters",
                category="approval",
                title="区级审批超时-已转交市级",
                content=content,
                related_id=req.id,
                related_type="replenishment"
            )


def _check_city_timeouts(db: Session, timeout: timedelta):
    pending_city = db.query(ReplenishmentRequest).filter(
        ReplenishmentRequest.city_approval_status == ApprovalStatus.PENDING,
        ReplenishmentRequest.district_approval_status.in_([
            ApprovalStatus.APPROVED, ApprovalStatus.TIMEOUT_ESCALATED
        ])
    ).all()

    for req in pending_city:
        city_start_time = req.district_approved_at or req.created_at
        elapsed = datetime.utcnow() - city_start_time
        if elapsed > timeout:
            req.city_approval_status = ApprovalStatus.TIMEOUT_ESCALATED
            req.city_reminder_count += 1
            hours = int(elapsed.total_seconds() / 3600)

            content = f"补货申请{req.id}市级审批已超时{hours}小时，已升级至上级主管部门处理"
            reminder = ApprovalReminder(
                request_id=req.id,
                level="city",
                reminder_count=req.city_reminder_count,
                escalated=True,
                content=content
            )
            db.add(reminder)

            push_message(
                db=db,
                target_role="headquarters",
                category="approval",
                title="市级审批超时-已升级至上级主管部门",
                content=content,
                related_id=req.id,
                related_type="replenishment"
            )


def mark_procurement_arrived(db: Session, procurement_id: int) -> ProcurementRecord:
    proc = db.query(ProcurementRecord).filter(ProcurementRecord.id == procurement_id).first()
    if not proc:
        raise ValueError("采购记录不存在")
    if proc.status != ProcurementStatus.PURCHASING:
        raise ValueError(f"当前状态{proc.status.value}不可标记到货，需为purchasing")

    proc.status = ProcurementStatus.ARRIVED
    proc.arrived_at = datetime.utcnow()

    push_message(
        db=db,
        target_role="headquarters",
        category="approval",
        title="采购物资已到货",
        content=f"补货申请{proc.request_id}的物资{proc.quantity}件已到货，待入库",
        related_id=proc.id,
        related_type="procurement"
    )

    db.commit()
    return proc


def mark_procurement_stored(db: Session, procurement_id: int) -> ProcurementRecord:
    proc = db.query(ProcurementRecord).filter(ProcurementRecord.id == procurement_id).first()
    if not proc:
        raise ValueError("采购记录不存在")
    if proc.status != ProcurementStatus.ARRIVED:
        raise ValueError(f"当前状态{proc.status.value}不可入库，需为arrived")

    proc.status = ProcurementStatus.STORED
    proc.stored_at = datetime.utcnow()

    req = db.query(ReplenishmentRequest).filter(ReplenishmentRequest.id == proc.request_id).first()
    if req:
        inv = db.query(MaterialInventory).filter(
            MaterialInventory.warehouse_id == req.warehouse_id,
            MaterialInventory.material_type == req.material_type
        ).first()
        if inv:
            inv.quantity += proc.quantity
            inv.updated_at = datetime.utcnow()

    push_message(
        db=db,
        target_role="headquarters",
        category="approval",
        title="采购物资已入库",
        content=f"补货申请{proc.request_id}的物资{proc.quantity}件已入库，库存已更新",
        related_id=proc.id,
        related_type="procurement"
    )

    db.commit()
    return proc
