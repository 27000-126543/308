import math
from datetime import datetime
from sqlalchemy.orm import Session
from models import (
    Warning, RiskLevel, ResourceAllocationPlan, ResourceAllocation,
    MaterialInventory, Warehouse, MaterialType, ApprovalStatus,
    AllocationStatus, RainStation, RainRecord, WaterLevelStation,
    WaterLevelRecord, GroundElevation
)
from services.push_service import push_approval, push_dispatch


def _get_disaster_point(db: Session, warning: Warning):
    rain_records = db.query(RainRecord).filter(
        RainRecord.rainfall_1h >= 10,
        RainRecord.recorded_at >= warning.created_at
    ).all()
    for rr in rain_records:
        station = db.query(RainStation).filter(RainStation.id == rr.station_id).first()
        if station and station.district == warning.district:
            return station.longitude, station.latitude

    wl_records = db.query(WaterLevelRecord).filter(
        WaterLevelRecord.recorded_at >= warning.created_at
    ).all()
    for wr in wl_records:
        station = db.query(WaterLevelStation).filter(WaterLevelStation.id == wr.station_id).first()
        if station and station.district == warning.district:
            return station.longitude, station.latitude

    ground = db.query(GroundElevation).filter(
        GroundElevation.district == warning.district
    ).order_by(GroundElevation.elevation.asc()).first()
    if ground:
        return ground.longitude, ground.latitude

    return None, None


def _get_district_center(db: Session, district: str):
    stations = db.query(RainStation).filter(RainStation.district == district).all()
    if stations:
        avg_lon = sum(s.longitude for s in stations) / len(stations)
        avg_lat = sum(s.latitude for s in stations) / len(stations)
        return avg_lon, avg_lat

    wl_stations = db.query(WaterLevelStation).filter(WaterLevelStation.district == district).all()
    if wl_stations:
        avg_lon = sum(s.longitude for s in wl_stations) / len(wl_stations)
        avg_lat = sum(s.latitude for s in wl_stations) / len(wl_stations)
        return avg_lon, avg_lat

    grounds = db.query(GroundElevation).filter(GroundElevation.district == district).all()
    if grounds:
        avg_lon = sum(g.longitude for g in grounds) / len(grounds)
        avg_lat = sum(g.latitude for g in grounds) / len(grounds)
        return avg_lon, avg_lat

    return 0, 0


def _haversine(lon1: float, lat1: float, lon2_or_tuple, lat2: float = None) -> float:
    if isinstance(lon2_or_tuple, tuple):
        lon2, lat2 = lon2_or_tuple
    else:
        lon2 = lon2_or_tuple
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def _estimate_arrival_hours(distance_km: float) -> float:
    avg_speed = 40.0
    return round(distance_km / avg_speed, 1)


def generate_resource_plan(db: Session, warning: Warning):
    if warning.risk_level not in (RiskLevel.ORANGE, RiskLevel.RED):
        return None

    district = warning.district
    disaster_lon, disaster_lat = _get_disaster_point(db, warning)

    local_warehouses = db.query(Warehouse).filter(Warehouse.district == district).all()
    all_warehouses = db.query(Warehouse).all()
    cross_district_warehouses = [w for w in all_warehouses if w.district != district]

    plan_data = {}
    allocations = []
    cross_district_summary = {}

    cross_alloc_warehouse_ids = set()

    for mat_type in MaterialType:
        needed = _calculate_needed_quantity(mat_type, warning.risk_level)
        local_allocated = 0
        cross_allocated = 0

        local_available = _collect_available(db, local_warehouses, mat_type, disaster_lon, disaster_lat, district)
        local_available.sort(key=lambda x: x["distance"])

        remaining = needed
        for item in local_available:
            if remaining <= 0:
                break
            alloc_qty = min(remaining, item["available"])
            allocations.append({
                "warehouse_id": item["warehouse_id"],
                "material_type": mat_type.value,
                "quantity": alloc_qty,
                "distance_km": round(item["distance"], 2),
                "is_cross_district": False,
                "estimated_arrival_hours": _estimate_arrival_hours(item["distance"])
            })
            local_allocated += alloc_qty
            remaining -= alloc_qty

        cross_used_districts = []
        if remaining > 0 and cross_district_warehouses:
            cross_available = _collect_available(db, cross_district_warehouses, mat_type, disaster_lon, disaster_lat, district)
            cross_available.sort(key=lambda x: x["distance"])

            for item in cross_available:
                if remaining <= 0:
                    break
                alloc_qty = min(remaining, item["available"])
                allocations.append({
                    "warehouse_id": item["warehouse_id"],
                    "material_type": mat_type.value,
                    "quantity": alloc_qty,
                    "distance_km": round(item["distance"], 2),
                    "is_cross_district": True,
                    "estimated_arrival_hours": _estimate_arrival_hours(item["distance"])
                })
                cross_allocated += alloc_qty
                cross_alloc_warehouse_ids.add(item["warehouse_id"])
                if item["district"] not in cross_used_districts:
                    cross_used_districts.append(item["district"])
                remaining -= alloc_qty

        plan_data[mat_type.value] = {
            "needed": needed,
            "local_allocated": local_allocated,
            "cross_district_allocated": cross_allocated,
            "total_allocated": needed - remaining,
            "shortage": max(0, remaining)
        }

        if cross_allocated > 0:
            cross_district_summary[mat_type.value] = {
                "cross_district_quantity": cross_allocated,
                "source_districts": cross_used_districts
            }

    plan = ResourceAllocationPlan(
        warning_id=warning.id,
        district=district,
        plan_data=plan_data,
        cross_district_summary=cross_district_summary,
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
            is_cross_district=alloc_data["is_cross_district"],
            status=AllocationStatus.LOCKED,
            estimated_arrival_hours=alloc_data["estimated_arrival_hours"]
        )
        db.add(alloc)

    push_approval(
        db=db,
        target_role="headquarters",
        title="应急资源调配方案待审批",
        content=f"{district}{warning.risk_level.value}色预警，已生成资源调配方案（含跨区支援），请指挥长审批",
        related_id=plan.id,
        related_type="resource_plan"
    )

    db.commit()
    return plan


def _collect_available(db: Session, warehouses, mat_type, disaster_lon, disaster_lat, district):
    result = []
    for wh in warehouses:
        inv = db.query(MaterialInventory).filter(
            MaterialInventory.warehouse_id == wh.id,
            MaterialInventory.material_type == mat_type
        ).first()
        if inv and (inv.quantity - inv.locked_quantity) > 0:
            if disaster_lon is not None and disaster_lat is not None:
                distance = _haversine(wh.longitude, wh.latitude, disaster_lon, disaster_lat)
            else:
                center_lon, center_lat = _get_district_center(db, district)
                distance = _haversine(wh.longitude, wh.latitude, center_lon, center_lat)
            available = inv.quantity - inv.locked_quantity
            result.append({
                "warehouse_id": wh.id,
                "available": available,
                "distance": distance,
                "district": wh.district
            })
    return result


def approve_resource_plan(db: Session, plan_id: int, approver: str) -> ResourceAllocationPlan:
    plan = db.query(ResourceAllocationPlan).filter(ResourceAllocationPlan.id == plan_id).first()
    if not plan:
        raise ValueError("调配方案不存在")

    if plan.approval_status == ApprovalStatus.APPROVED:
        return plan

    plan.approval_status = ApprovalStatus.APPROVED
    plan.approver = approver
    plan.approved_at = datetime.utcnow()

    allocations = db.query(ResourceAllocation).filter(ResourceAllocation.plan_id == plan.id).all()
    for alloc in allocations:
        alloc.status = AllocationStatus.LOCKED
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
        content=f"{plan.district}资源调配方案已由{approver}审批通过，物资已锁定待出库",
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


def confirm_shipment(db: Session, allocation_id: int) -> ResourceAllocation:
    alloc = db.query(ResourceAllocation).filter(ResourceAllocation.id == allocation_id).first()
    if not alloc:
        raise ValueError("调配记录不存在")
    if alloc.status != AllocationStatus.LOCKED:
        raise ValueError(f"当前状态{alloc.status.value}不可出库，需为locked状态")

    alloc.status = AllocationStatus.SHIPPED
    alloc.shipped_at = datetime.utcnow()

    inv = db.query(MaterialInventory).filter(
        MaterialInventory.warehouse_id == alloc.warehouse_id,
        MaterialInventory.material_type == alloc.material_type
    ).first()
    if inv:
        inv.quantity -= alloc.quantity
        inv.locked_quantity -= alloc.quantity
        inv.updated_at = datetime.utcnow()

    push_dispatch(
        db=db,
        target_role="headquarters",
        title="物资已出库",
        content=f"仓库{alloc.warehouse_id}{alloc.material_type.value}{alloc.quantity}件已出库，预计{alloc.estimated_arrival_hours}小时到达",
        related_id=alloc.id,
        related_type="allocation"
    )

    db.commit()
    return alloc


def confirm_arrival(db: Session, allocation_id: int, receiver: str) -> ResourceAllocation:
    alloc = db.query(ResourceAllocation).filter(ResourceAllocation.id == allocation_id).first()
    if not alloc:
        raise ValueError("调配记录不存在")
    if alloc.status != AllocationStatus.SHIPPED:
        raise ValueError(f"当前状态{alloc.status.value}不可签收，需为shipped状态")

    alloc.status = AllocationStatus.ARRIVED
    alloc.arrived_at = datetime.utcnow()
    alloc.receiver = receiver

    push_dispatch(
        db=db,
        target_role="headquarters",
        title="物资已到达",
        content=f"{alloc.material_type.value}{alloc.quantity}件已到达，签收人：{receiver}",
        related_id=alloc.id,
        related_type="allocation"
    )

    db.commit()
    return alloc


def report_consumption(db: Session, allocation_id: int, consumed_quantity: int) -> ResourceAllocation:
    from datetime import datetime
    alloc = db.query(ResourceAllocation).filter(ResourceAllocation.id == allocation_id).first()
    if not alloc:
        raise ValueError("调配记录不存在")
    if alloc.status not in (AllocationStatus.ARRIVED, AllocationStatus.CONSUMED):
        raise ValueError(f"当前状态{alloc.status.value}不可报消耗，需为arrived状态")

    if consumed_quantity > alloc.quantity - alloc.consumed_quantity:
        raise ValueError("消耗数量超过剩余量")

    alloc.consumed_quantity += consumed_quantity
    alloc.consumed_at = datetime.utcnow()

    if alloc.consumed_quantity >= alloc.quantity:
        alloc.status = AllocationStatus.CONSUMED

    db.commit()
    return alloc


def _calculate_needed_quantity(mat_type: MaterialType, risk_level: RiskLevel) -> int:
    base = {
        MaterialType.WATER_PUMP: 10,
        MaterialType.SANDBAG: 500,
        MaterialType.ASSAULT_BOAT: 5,
    }
    multiplier = 3 if risk_level == RiskLevel.RED else 2
    return base.get(mat_type, 0) * multiplier
