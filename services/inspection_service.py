import math
from datetime import datetime
from sqlalchemy.orm import Session
from models import (
    InspectionOrder, InspectionReport, TrafficControlPlan,
    Warning, GuideScreen, ApprovalStatus, TrafficControlType,
    WorkOrderStatus
)
from services.push_service import push_work_order, push_approval, push_dispatch
from services.risk_service import record_waterlogging_event


def create_inspection_order(db: Session, warning_id: int, inspector_name: str,
                             district: str, location: str, longitude: float,
                             latitude: float) -> InspectionOrder:
    order = InspectionOrder(
        warning_id=warning_id,
        inspector_name=inspector_name,
        district=district,
        location=location,
        longitude=longitude,
        latitude=latitude,
        status=WorkOrderStatus.ASSIGNED
    )
    db.add(order)
    db.flush()

    push_work_order(
        db=db,
        target_role="inspector",
        title="巡查工单",
        content=f"请前往{district}{location}进行积水巡查，预警编号{warning_id}",
        related_id=order.id,
        related_type="inspection_order"
    )

    db.commit()
    return order


def submit_inspection_report(db: Session, order_id: int, water_depth: float,
                              photo_url: str = None, description: str = "") -> InspectionReport:
    order = db.query(InspectionOrder).filter(InspectionOrder.id == order_id).first()
    if not order:
        raise ValueError("巡查工单不存在")

    report = InspectionReport(
        order_id=order_id,
        water_depth=water_depth,
        photo_url=photo_url,
        description=description
    )
    db.add(report)

    order.status = WorkOrderStatus.COMPLETED
    order.completed_at = datetime.utcnow()

    record_waterlogging_event(
        db=db,
        location=order.location,
        district=order.district,
        longitude=order.longitude,
        latitude=order.latitude,
        water_depth=water_depth,
        warning_id=order.warning_id
    )

    needs_control = _check_adjacent_points(db, order, water_depth)
    report.needs_traffic_control = needs_control
    report.adjacent_confirmed = True

    if needs_control:
        _generate_traffic_control_plan(db, report, order)

    db.commit()
    return report


def _check_adjacent_points(db: Session, order: InspectionOrder, water_depth: float) -> bool:
    if water_depth < 0.15:
        return False

    nearby_reports = db.query(InspectionReport).join(InspectionOrder).filter(
        InspectionOrder.district == order.district,
        InspectionOrder.id != order.id
    ).all()

    for nr in nearby_reports:
        no = nr.order
        if not no:
            continue
        dist = _haversine(order.longitude, order.latitude, no.longitude, no.latitude)
        if dist < 1.0 and nr.water_depth >= 0.15:
            return True

    if water_depth >= 0.3:
        return True

    return False


def _generate_traffic_control_plan(db: Session, report: InspectionReport, order: InspectionOrder):
    control_type = TrafficControlType.ROAD_CLOSURE if report.water_depth >= 0.3 else TrafficControlType.TRAFFIC_DIVERSION

    plan = TrafficControlPlan(
        inspection_report_id=report.id,
        district=order.district,
        location=order.location,
        control_type=control_type,
        description=f"{order.district}{order.location}积水深度{report.water_depth}m，建议{'封路' if control_type == TrafficControlType.ROAD_CLOSURE else '调流'}管制",
        approval_status=ApprovalStatus.PENDING
    )
    db.add(plan)
    db.flush()

    push_approval(
        db=db,
        target_role="traffic_dept",
        title="交通管制方案待审批",
        content=plan.description,
        related_id=plan.id,
        related_type="traffic_control"
    )


def approve_traffic_control(db: Session, plan_id: int, approver: str) -> TrafficControlPlan:
    plan = db.query(TrafficControlPlan).filter(TrafficControlPlan.id == plan_id).first()
    if not plan:
        raise ValueError("管制方案不存在")

    plan.approval_status = ApprovalStatus.APPROVED
    plan.approver = approver
    plan.approved_at = datetime.utcnow()

    _update_guide_screens(db, plan)

    push_dispatch(
        db=db,
        target_role="traffic_dept",
        title="交通管制已审批",
        content=f"{plan.district}{plan.location}交通管制方案已审批通过，诱导屏已更新",
        related_id=plan.id,
        related_type="traffic_control"
    )

    db.commit()
    return plan


def _update_guide_screens(db: Session, plan: TrafficControlPlan):
    screens = db.query(GuideScreen).filter(GuideScreen.district == plan.district).all()
    for screen in screens:
        dist = _haversine(screen.longitude, screen.latitude, 0, 0)
        screen.current_content = f"【交通管制】{plan.location}{plan.description}"
        screen.updated_at = datetime.utcnow()

    plan.screen_updated = True


def _haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    return R * c
