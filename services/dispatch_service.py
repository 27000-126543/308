import math
from datetime import datetime
from sqlalchemy.orm import Session
from models import (
    Warning, RiskLevel, ResourceAllocationPlan, ResourceAllocation,
    MaterialInventory, Warehouse, MaterialType, ApprovalStatus
)
from services.push_service import push_approval, push_dispatch


def generate_resource_plan(db: Session, warning: Warning):
    if warning.risk_level not in (RiskLevel.ORANGE, RiskLevel.RED):
        return None

    district = warning.district
    warehouses = db.query(Warehouse).filter(Warehouse.district == district).all()

    if not warehouses:
        warehouses = db.query(Warehouse).all()

    plan_data = {}
    allocations = []

    for mat_type in MaterialType:
        needed = _calculate_needed_quantity(mat_type, warning.risk_level)
        available_list = []

        for wh in warehouses:
            inv = db.query(MaterialInventory).filter(
                MaterialInventory.warehouse_id == wh.id,
                MaterialInventory.material_type == mat_type
            ).first()
            if inv and (inv.quantity - inv.locked_quantity) > 0:
                distance = _calc_distance_from_warning(wh, warning)
                available = inv.quantity - inv.locked_quantity
                available_list.append({
                    "warehouse_id": wh.id,
                    "warehouse_name": wh.name,
                    "available": available,
                    "distance": distance
                })

        available_list.sort(key=lambda x: x["distance"])

        remaining = needed
        for item in available_list:
            if remaining <= 0:
                break
            alloc_qty = min(remaining, item["available"])
            allocations.append({
                "warehouse_id": item["warehouse_id"],
                "material_type": mat_type.value,
                "quantity": alloc_qty,
                "distance_km": round(item["distance"], 2)
            })
            remaining -= alloc_qty

        plan_data[mat_type.value] = {
            "needed": needed,
            "allocated": needed - remaining,
            "shortage": max(0, remaining)
        }

    plan = ResourceAllocationPlan(
        warning_id=warning.id,
        district=district,
        plan_data=plan_data,
        approval_status=ApprovalStatus.PENDING
    )
    db.add(plan)
    db.flush()

    for alloc_data in allocations:
        alloc = ResourceAllocation(
            plan_id=plan.id,
            warehouse_id=alloc_data["warehouse_id"],
            material_type=MaterialType(alloc_data["material_type"]),
            quantity=alloc_data["quantity"],
            distance_km=alloc_data["distance_km"],
            locked=False
        )
        db.add(alloc)

    push_approval(
        db=db,
        target_role="headquarters",
        title="应急资源调配方案待审批",
        content=f"{district}{warning.risk_level.value}色预警，已生成资源调配方案，请指挥长审批",
        related_id=plan.id,
        related_type="resource_plan"
    )

    db.commit()
    return plan


def approve_resource_plan(db: Session, plan_id: int, approver: str) -> ResourceAllocationPlan:
    plan = db.query(ResourceAllocationPlan).filter(ResourceAllocationPlan.id == plan_id).first()
    if not plan:
        raise ValueError("调配方案不存在")

    plan.approval_status = ApprovalStatus.APPROVED
    plan.approver = approver
    plan.approved_at = datetime.utcnow()

    allocations = db.query(ResourceAllocation).filter(ResourceAllocation.plan_id == plan.id).all()
    for alloc in allocations:
        alloc.locked = True
        inv = db.query(MaterialInventory).filter(
            MaterialInventory.warehouse_id == alloc.warehouse_id,
            MaterialInventory.material_type == alloc.material_type
        ).first()
        if inv:
            inv.locked_quantity += alloc.quantity
            inv.updated_at = datetime.utcnow()

    push_dispatch(
        db=db,
        target_role="headquarters",
        title="资源调配方案已审批",
        content=f"{plan.district}资源调配方案已由{approver}审批通过，物资已锁定",
        related_id=plan.id,
        related_type="resource_plan"
    )

    db.commit()
    return plan


def reject_resource_plan(db: Session, plan_id: int, approver: str) -> ResourceAllocationPlan:
    plan = db.query(ResourceAllocationPlan).filter(ResourceAllocationPlan.id == plan_id).first()
    if not plan:
        raise ValueError("调配方案不存在")

    plan.approval_status = ApprovalStatus.REJECTED
    plan.approver = approver
    plan.approved_at = datetime.utcnow()
    db.commit()
    return plan


def _calculate_needed_quantity(mat_type: MaterialType, risk_level: RiskLevel) -> int:
    base = {
        MaterialType.WATER_PUMP: 10,
        MaterialType.SANDBAG: 500,
        MaterialType.ASSAULT_BOAT: 5,
    }
    multiplier = 3 if risk_level == RiskLevel.RED else 2
    return base.get(mat_type, 0) * multiplier


def _calc_distance_from_warning(warehouse: Warehouse, warning: Warning) -> float:
    return _haversine(warehouse.longitude, warehouse.latitude, 0, 0)


def _haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    return R * c
