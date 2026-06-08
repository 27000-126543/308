from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from models import (
    Warning, RiskLevel, PumpDispatch, ResourceAllocationPlan,
    ResourceAllocation, AllocationStatus, InspectionOrder,
    InspectionReport, TrafficControlPlan, PumpStation,
    PumpOperationLog, ReplenishmentRequest, ApprovalReminder,
    ProcurementRecord, RainRecord, RainStation, WaterLevelRecord,
    WaterLevelStation, ApprovalStatus, MaterialType, Warehouse
)


def get_warning_timeline(db: Session, warning_id: int):
    warning = db.query(Warning).filter(Warning.id == warning_id).first()
    if not warning:
        return None

    nodes = []
    t0 = warning.created_at

    nodes.append(_make_node("warning_triggered", "active", None, t0, None, {
        "district": warning.district, "risk_level": warning.risk_level.value,
        "rainfall_intensity": warning.rainfall_intensity,
        "pipe_usage_ratio": warning.pipe_usage_ratio
    }))

    dispatches = db.query(PumpDispatch).filter(
        PumpDispatch.warning_id == warning_id
    ).all()
    if dispatches:
        for d in dispatches:
            station = db.query(PumpStation).filter(PumpStation.id == d.station_id).first()
            dur = (d.issued_at - t0).total_seconds() / 60 if d.issued_at else None
            nodes.append(_make_node(
                "pump_dispatch", d.status, None, d.issued_at, dur,
                {"station": station.name if station else "", "target": d.target_discharge}
            ))
    else:
        nodes.append(_make_node("pump_dispatch", "pending", None, None, None, None))

    plan = db.query(ResourceAllocationPlan).filter(
        ResourceAllocationPlan.warning_id == warning_id
    ).first()
    if plan:
        dur = (plan.created_at - t0).total_seconds() / 60
        nodes.append(_make_node("resource_plan_created", plan.approval_status.value, None, plan.created_at, dur, {
            "plan_id": plan.id, "plan_data": plan.plan_data
        }))

        if plan.approval_status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
            dur2 = (plan.approved_at - plan.created_at).total_seconds() / 60 if plan.approved_at else None
            nodes.append(_make_node("resource_plan_approved", plan.approval_status.value, plan.approver, plan.approved_at, dur2, None))
        elif plan.approval_status == ApprovalStatus.PENDING:
            nodes.append(_make_node("resource_plan_approved", "pending", None, None, None, None))

        allocs = db.query(ResourceAllocation).filter(
            ResourceAllocation.plan_id == plan.id
        ).all()

        shipped = [a for a in allocs if a.shipped_at]
        if shipped:
            first_ship = min(a.shipped_at for a in shipped)
            dur = (first_ship - (plan.approved_at or t0)).total_seconds() / 60
            nodes.append(_make_node("material_shipped", "completed", None, first_ship, dur, {
                "count": len(shipped), "total_qty": sum(a.quantity for a in shipped)
            }))
        elif plan.approval_status == ApprovalStatus.APPROVED:
            nodes.append(_make_node("material_shipped", "pending", None, None, None, None))

        arrived = [a for a in allocs if a.arrived_at]
        if arrived:
            first_arr = min(a.arrived_at for a in arrived)
            dur = (first_arr - (shipped[0].shipped_at if shipped else t0)).total_seconds() / 60
            nodes.append(_make_node("material_arrived", "completed", arrived[0].receiver if arrived else None, first_arr, dur, {
                "count": len(arrived), "total_qty": sum(a.quantity for a in arrived)
            }))
        elif shipped:
            nodes.append(_make_node("material_arrived", "pending", None, None, None, None))

        consumed = [a for a in allocs if a.consumed_quantity > 0]
        if consumed:
            nodes.append(_make_node("material_consumed", "partial", None, None, None, {
                "total_consumed": sum(a.consumed_quantity for a in consumed),
                "total_allocated": sum(a.quantity for a in allocs)
            }))
    else:
        for nt in ["resource_plan_created", "resource_plan_approved", "material_shipped", "material_arrived", "material_consumed"]:
            nodes.append(_make_node(nt, "pending", None, None, None, None))

    orders = db.query(InspectionOrder).filter(
        InspectionOrder.warning_id == warning_id
    ).all()
    if orders:
        for o in orders:
            nodes.append(_make_node("inspection_assigned", o.status.value, o.inspector_name, o.created_at,
                                    (o.created_at - t0).total_seconds() / 60, {"location": o.location}))
            if o.status.value in ("completed", "closed") and o.completed_at:
                reports = db.query(InspectionReport).filter(InspectionReport.order_id == o.id).all()
                for r in reports:
                    nodes.append(_make_node("inspection_reported", "completed", o.inspector_name, r.reported_at,
                                            (r.reported_at - o.created_at).total_seconds() / 60,
                                            {"water_depth": r.water_depth, "needs_control": r.needs_traffic_control}))
                    if r.needs_traffic_control:
                        tc = db.query(TrafficControlPlan).filter(
                            TrafficControlPlan.inspection_report_id == r.id
                        ).first()
                        if tc:
                            nodes.append(_make_node("traffic_control", tc.approval_status.value, tc.approver, tc.created_at, None,
                                                    {"type": tc.control_type.value, "screen_updated": tc.screen_updated}))
    else:
        nodes.append(_make_node("inspection_assigned", "pending", None, None, None, None))

    return {
        "warning_id": warning.id,
        "district": warning.district,
        "risk_level": warning.risk_level,
        "created_at": warning.created_at,
        "nodes": nodes
    }


def _make_node(node_type: str, status: str, handler, occurred_at, duration_minutes, details):
    return {
        "node_type": node_type,
        "status": status,
        "handler": handler,
        "occurred_at": occurred_at,
        "duration_minutes": round(duration_minutes, 1) if duration_minutes is not None else None,
        "details": details
    }


def generate_incident_review(db: Session, warning_id: int = None, district: str = None,
                              start_date: date = None, end_date: date = None):
    start = datetime.combine(start_date, datetime.min.time()) if start_date else None
    end = datetime.combine(end_date, datetime.max.time()) if end_date else None

    query = db.query(Warning)
    if warning_id:
        query = query.filter(Warning.id == warning_id)
    if district:
        query = query.filter(Warning.district == district)
    if start:
        query = query.filter(Warning.created_at >= start)
    if end:
        query = query.filter(Warning.created_at <= end)
    warnings = query.order_by(Warning.created_at.desc()).all()

    if not warnings:
        return None

    review_district = district or warnings[0].district
    result = {
        "warning_id": warning_id,
        "district": review_district,
        "start_date": start_date,
        "end_date": end_date,
        "rainfall_summary": _build_rainfall_summary(db, review_district, start, end),
        "risk_level_changes": _build_risk_changes(warnings),
        "pump_discharge_summary": _build_pump_summary(db, review_district, start, end),
        "work_order_summary": _build_work_order_summary(db, review_district, start, end),
        "material_summary": _build_material_summary(db, review_district, start, end),
        "replenishment_summary": _build_replenishment_summary(db, review_district, start, end)
    }
    return result


def _build_rainfall_summary(db, district, start, end):
    stations = db.query(RainStation).filter(RainStation.district == district).all()
    if not stations:
        return None
    station_ids = [s.id for s in stations]
    query = db.query(RainRecord).filter(RainRecord.station_id.in_(station_ids))
    if start:
        query = query.filter(RainRecord.recorded_at >= start)
    if end:
        query = query.filter(RainRecord.recorded_at <= end)
    records = query.all()
    if not records:
        return None
    return {
        "station_count": len(stations),
        "max_1h": max((r.rainfall_1h for r in records), default=0),
        "max_3h": max((r.rainfall_3h for r in records), default=0),
        "max_24h": max((r.rainfall_24h for r in records), default=0),
        "record_count": len(records)
    }


def _build_risk_changes(warnings):
    return [{"risk_level": w.risk_level.value, "time": str(w.created_at), "rainfall": w.rainfall_intensity} for w in warnings]


def _build_pump_summary(db, district, start, end):
    stations = db.query(PumpStation).filter(PumpStation.district == district).all()
    if not stations:
        return None
    station_ids = [s.id for s in stations]
    query = db.query(PumpOperationLog).filter(PumpOperationLog.station_id.in_(station_ids))
    if start:
        query = query.filter(PumpOperationLog.recorded_at >= start)
    if end:
        query = query.filter(PumpOperationLog.recorded_at <= end)
    logs = query.all()
    return {
        "total_discharge": sum(l.discharge_volume for l in logs),
        "total_energy": sum(l.energy_consumption for l in logs),
        "station_count": len(stations),
        "log_count": len(logs)
    }


def _build_work_order_summary(db, district, start, end):
    query = db.query(InspectionOrder).filter(InspectionOrder.district == district)
    if start:
        query = query.filter(InspectionOrder.created_at >= start)
    if end:
        query = query.filter(InspectionOrder.created_at <= end)
    orders = query.all()
    completed = [o for o in orders if o.status.value in ("completed", "closed")]
    return {
        "total": len(orders),
        "completed": len(completed),
        "pending": len(orders) - len(completed)
    }


def _build_material_summary(db, district, start, end):
    query = db.query(ResourceAllocation).join(ResourceAllocationPlan).filter(
        ResourceAllocationPlan.district == district
    )
    if start:
        query = query.filter(ResourceAllocationPlan.approved_at >= start)
    if end:
        query = query.filter(ResourceAllocationPlan.approved_at <= end)
    allocs = query.all()

    total_allocated = sum(a.quantity for a in allocs)
    total_shipped = sum(a.quantity for a in allocs if a.status in (AllocationStatus.SHIPPED, AllocationStatus.ARRIVED, AllocationStatus.CONSUMED))
    total_arrived = sum(a.quantity for a in allocs if a.status in (AllocationStatus.ARRIVED, AllocationStatus.CONSUMED))
    total_consumed = sum(a.consumed_quantity for a in allocs)
    cross_district = sum(a.quantity for a in allocs if a.is_cross_district)

    return {
        "total_allocated": total_allocated,
        "total_shipped": total_shipped,
        "total_arrived": total_arrived,
        "total_consumed": total_consumed,
        "cross_district_quantity": cross_district
    }


def _build_replenishment_summary(db, district, start, end):
    wh_ids = [w.id for w in db.query(Warehouse).filter(Warehouse.district == district).all()]
    if not wh_ids:
        return None
    query = db.query(ReplenishmentRequest).filter(ReplenishmentRequest.warehouse_id.in_(wh_ids))
    if start:
        query = query.filter(ReplenishmentRequest.created_at >= start)
    if end:
        query = query.filter(ReplenishmentRequest.created_at <= end)
    reqs = query.all()

    reminders_count = 0
    procurements_count = 0
    for req in reqs:
        reminders_count += db.query(ApprovalReminder).filter(ApprovalReminder.request_id == req.id).count()
        procurements_count += db.query(ProcurementRecord).filter(ProcurementRecord.request_id == req.id).count()

    return {
        "total_requests": len(reqs),
        "district_approved": len([r for r in reqs if r.district_approval_status in (ApprovalStatus.APPROVED, ApprovalStatus.TIMEOUT_ESCALATED)]),
        "city_approved": len([r for r in reqs if r.city_approval_status == ApprovalStatus.APPROVED]),
        "reminders_count": reminders_count,
        "procurements_count": procurements_count
    }
