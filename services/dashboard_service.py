from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models import (
    Warning, RiskLevel, RainRecord, RainStation, WaterLevelRecord,
    WaterLevelStation, PumpDispatch, PumpStation, PumpOperationLog,
    ResourceAllocationPlan, ResourceAllocation, AllocationStatus,
    InspectionOrder, InspectionReport, TrafficControlPlan,
    ReplenishmentRequest, ApprovalStatus, ProcurementRecord, ProcurementStatus,
    UrgeRecord, Warehouse, MaterialType, ApprovalReminder
)
from schemas import DashboardModule, DashboardResponse, UrgeRecordResponse


def get_dashboard(db: Session, warning_id: int) -> dict:
    warning = db.query(Warning).filter(Warning.id == warning_id).first()
    if not warning:
        return None

    district = warning.district
    modules = []

    modules.append(_build_rain_water_module(db, warning))
    modules.append(_build_pump_module(db, warning))
    modules.append(_build_material_module(db, warning))
    modules.append(_build_inspection_module(db, warning))
    modules.append(_build_traffic_module(db, warning))
    modules.append(_build_replenishment_module(db, warning))

    urges = db.query(UrgeRecord).filter(
        UrgeRecord.warning_id == warning_id
    ).order_by(UrgeRecord.last_urged_at.desc()).all()

    return {
        "warning_id": warning.id,
        "district": warning.district,
        "risk_level": warning.risk_level.value,
        "created_at": warning.created_at,
        "modules": modules,
        "urge_records": [UrgeRecordResponse.model_validate(u) for u in urges]
    }


def _build_rain_water_module(db, warning):
    district = warning.district
    rain_stations = db.query(RainStation).filter(RainStation.district == district).all()
    water_stations = db.query(WaterLevelStation).filter(WaterLevelStation.district == district).all()

    latest_rain = {}
    for s in rain_stations:
        rec = db.query(RainRecord).filter(RainRecord.station_id == s.id).order_by(RainRecord.recorded_at.desc()).first()
        if rec:
            latest_rain[s.name] = {"1h": rec.rainfall_1h, "3h": rec.rainfall_3h, "24h": rec.rainfall_24h}

    latest_water = {}
    for s in water_stations:
        rec = db.query(WaterLevelRecord).filter(WaterLevelRecord.station_id == s.id).order_by(WaterLevelRecord.recorded_at.desc()).first()
        if rec:
            latest_water[s.name] = {"level": rec.water_level, "trend": rec.trend}

    return {
        "module_name": "rain_water",
        "status": "active" if latest_rain else "no_data",
        "responsible": "监测中心",
        "next_action": "持续监测降雨水位变化",
        "timeout_risk": warning.risk_level in (RiskLevel.ORANGE, RiskLevel.RED),
        "related_ids": [s.id for s in rain_stations] + [s.id for s in water_stations],
        "details": {"rain": latest_rain, "water": latest_water, "risk_level": warning.risk_level.value}
    }


def _build_pump_module(db, warning):
    dispatches = db.query(PumpDispatch).filter(PumpDispatch.warning_id == warning.id).all()
    if not dispatches:
        return {
            "module_name": "pump_dispatch",
            "status": "pending",
            "responsible": None,
            "next_action": "等待泵站预排指令",
            "timeout_risk": False,
            "related_ids": [],
            "details": None
        }

    items = []
    timeout_risk = False
    responsible = None
    for d in dispatches:
        station = db.query(PumpStation).filter(PumpStation.id == d.station_id).first()
        acked = d.acknowledged_at is not None
        if not acked and d.issued_at and (datetime.utcnow() - d.issued_at) > timedelta(minutes=30):
            timeout_risk = True
        if station and not responsible:
            responsible = station.name
        items.append({
            "station": station.name if station else "",
            "status": d.status,
            "target_discharge": d.target_discharge,
            "acknowledged": acked
        })

    all_acked = all(d.acknowledged_at for d in dispatches)
    next_action = "等待泵站确认" if not all_acked else "执行预排中"

    return {
        "module_name": "pump_dispatch",
        "status": "executing" if all_acked else "issued",
        "responsible": responsible,
        "next_action": next_action,
        "timeout_risk": timeout_risk,
        "related_ids": [d.id for d in dispatches],
        "details": {"dispatches": items}
    }


def _build_material_module(db, warning):
    plan = db.query(ResourceAllocationPlan).filter(
        ResourceAllocationPlan.warning_id == warning.id
    ).first()
    if not plan:
        return {
            "module_name": "material_allocation",
            "status": "pending",
            "responsible": None,
            "next_action": "等待生成资源调配方案",
            "timeout_risk": False,
            "related_ids": [],
            "details": None
        }

    allocs = db.query(ResourceAllocation).filter(ResourceAllocation.plan_id == plan.id).all()
    status_map = {}
    for a in allocs:
        st = a.status.value
        status_map[st] = status_map.get(st, 0) + a.quantity

    if plan.approval_status == ApprovalStatus.PENDING:
        return {
            "module_name": "material_allocation",
            "status": "awaiting_approval",
            "responsible": None,
            "next_action": "等待指挥长审批",
            "timeout_risk": False,
            "related_ids": [plan.id],
            "details": {"plan_id": plan.id, "plan_data": plan.plan_data}
        }

    not_shipped = [a for a in allocs if a.status == AllocationStatus.LOCKED]
    not_arrived = [a for a in allocs if a.status == AllocationStatus.SHIPPED]
    not_consumed = [a for a in allocs if a.status == AllocationStatus.ARRIVED]

    timeout_risk = False
    for a in allocs:
        if a.shipped_at and a.arrived_at is None:
            est = a.estimated_arrival_hours or 4
            if (datetime.utcnow() - a.shipped_at) > timedelta(hours=est):
                timeout_risk = True

    if not_shipped:
        next_action = "等待仓库出库"
        responsible = "仓储负责人"
        status = "locked"
    elif not_arrived:
        next_action = "等待现场签收"
        responsible = "现场接收人"
        status = "shipped"
    elif not_consumed:
        next_action = "等待消耗上报"
        responsible = "现场负责人"
        status = "arrived"
    else:
        next_action = None
        responsible = None
        status = "consumed"

    return {
        "module_name": "material_allocation",
        "status": status,
        "responsible": responsible,
        "next_action": next_action,
        "timeout_risk": timeout_risk,
        "related_ids": [plan.id] + [a.id for a in allocs],
        "details": {"plan_id": plan.id, "status_summary": status_map, "cross_district_summary": plan.cross_district_summary}
    }


def _build_inspection_module(db, warning):
    orders = db.query(InspectionOrder).filter(
        InspectionOrder.warning_id == warning.id
    ).all()
    if not orders:
        return {
            "module_name": "inspection",
            "status": "pending",
            "responsible": None,
            "next_action": "等待派遣巡查人员",
            "timeout_risk": False,
            "related_ids": [],
            "details": None
        }

    timeout_risk = False
    for o in orders:
        if o.status.value not in ("completed", "closed") and o.created_at:
            if (datetime.utcnow() - o.created_at) > timedelta(hours=2):
                timeout_risk = True

    pending = [o for o in orders if o.status.value not in ("completed", "closed")]
    completed = [o for o in orders if o.status.value in ("completed", "closed")]

    next_action = "等待巡查上报" if pending else None
    responsible = orders[0].inspector_name if orders else None

    return {
        "module_name": "inspection",
        "status": "in_progress" if pending else "completed",
        "responsible": responsible,
        "next_action": next_action,
        "timeout_risk": timeout_risk,
        "related_ids": [o.id for o in orders],
        "details": {"total": len(orders), "completed": len(completed), "pending": len(pending)}
    }


def _build_traffic_module(db, warning):
    plans = []
    orders = db.query(InspectionOrder).filter(InspectionOrder.warning_id == warning.id).all()
    for o in orders:
        reports = db.query(InspectionReport).filter(InspectionReport.order_id == o.id).all()
        for r in reports:
            tc = db.query(TrafficControlPlan).filter(
                TrafficControlPlan.inspection_report_id == r.id
            ).first()
            if tc:
                plans.append(tc)

    if not plans:
        needs = any(
            db.query(InspectionReport).filter(
                InspectionReport.order_id == o.id,
                InspectionReport.needs_traffic_control == True
            ).first()
            for o in orders
        ) if orders else False

        return {
            "module_name": "traffic_control",
            "status": "needed" if needs else "not_needed",
            "responsible": None,
            "next_action": "等待生成交通管制方案" if needs else None,
            "timeout_risk": False,
            "related_ids": [],
            "details": None
        }

    pending_approval = [p for p in plans if p.approval_status == ApprovalStatus.PENDING]
    timeout_risk = any(
        p.created_at and (datetime.utcnow() - p.created_at) > timedelta(hours=1)
        for p in pending_approval
    )

    return {
        "module_name": "traffic_control",
        "status": "awaiting_approval" if pending_approval else "approved",
        "responsible": plans[0].approver if plans else None,
        "next_action": "等待交警审批" if pending_approval else None,
        "timeout_risk": timeout_risk,
        "related_ids": [p.id for p in plans],
        "details": {"total": len(plans), "pending": len(pending_approval)}
    }


def _build_replenishment_module(db, warning):
    district = warning.district
    wh_ids = [w.id for w in db.query(Warehouse).filter(Warehouse.district == district).all()]
    if not wh_ids:
        return {
            "module_name": "replenishment",
            "status": "not_needed",
            "responsible": None,
            "next_action": None,
            "timeout_risk": False,
            "related_ids": [],
            "details": None
        }

    reqs = db.query(ReplenishmentRequest).filter(
        ReplenishmentRequest.warehouse_id.in_(wh_ids)
    ).all()

    if not reqs:
        return {
            "module_name": "replenishment",
            "status": "not_needed",
            "responsible": None,
            "next_action": None,
            "timeout_risk": False,
            "related_ids": [],
            "details": None
        }

    timeout_risk = False
    for req in reqs:
        if req.district_approval_status == ApprovalStatus.PENDING:
            if req.created_at and (datetime.utcnow() - req.created_at) > timedelta(hours=3):
                timeout_risk = True
        elif req.city_approval_status == ApprovalStatus.PENDING:
            if req.district_approved_at and (datetime.utcnow() - req.district_approved_at) > timedelta(hours=3):
                timeout_risk = True

    pending_district = [r for r in reqs if r.district_approval_status == ApprovalStatus.PENDING]
    pending_city = [r for r in reqs if r.city_approval_status == ApprovalStatus.PENDING and r.district_approval_status in (ApprovalStatus.APPROVED, ApprovalStatus.TIMEOUT_ESCALATED)]

    procs = db.query(ProcurementRecord).filter(
        ProcurementRecord.request_id.in_([r.id for r in reqs])
    ).all()
    pending_store = [p for p in procs if p.status == ProcurementStatus.ARRIVED]

    if pending_district:
        next_action = "等待区级审批"
        responsible = "区级审批人"
        status = "pending_district"
    elif pending_city:
        next_action = "等待市级审批"
        responsible = "市级审批人"
        status = "pending_city"
    elif pending_store:
        next_action = "等待采购入库"
        responsible = "采购负责人"
        status = "procurement_arrived"
    elif procs and all(p.status == ProcurementStatus.STORED for p in procs):
        next_action = None
        responsible = None
        status = "completed"
    else:
        next_action = "采购中"
        responsible = "采购负责人"
        status = "purchasing"

    return {
        "module_name": "replenishment",
        "status": status,
        "responsible": responsible,
        "next_action": next_action,
        "timeout_risk": timeout_risk,
        "related_ids": [r.id for r in reqs] + [p.id for p in procs],
        "details": {
            "total_requests": len(reqs),
            "pending_district": len(pending_district),
            "pending_city": len(pending_city),
            "procurements": len(procs),
            "pending_store": len(pending_store)
        }
    }
