import math
from datetime import datetime
from sqlalchemy.orm import Session
from models import (
    PumpDevice, MaintenanceOrder, MaintenanceTeam, PumpStation,
    DeviceStatus, WorkOrderStatus, PumpOperationLog
)
from services.push_service import push_work_order


def check_maintenance_cycles(db: Session):
    devices = db.query(PumpDevice).filter(
        PumpDevice.status.in_([DeviceStatus.RUNNING, DeviceStatus.STOPPED])
    ).all()

    for device in devices:
        hours_since_maintenance = device.running_hours
        if device.last_maintenance_at:
            logs = db.query(PumpOperationLog).filter(
                PumpOperationLog.station_id == device.station_id,
                PumpOperationLog.recorded_at >= device.last_maintenance_at
            ).all()
            hours_since_maintenance = sum(log.running_hours for log in logs)

        if hours_since_maintenance >= device.maintenance_cycle_hours:
            existing = db.query(MaintenanceOrder).filter(
                MaintenanceOrder.device_id == device.id,
                MaintenanceOrder.status.in_([WorkOrderStatus.PENDING, WorkOrderStatus.ASSIGNED])
            ).first()
            if not existing:
                _create_maintenance_order(db, device)


def _create_maintenance_order(db: Session, device: PumpDevice):
    station = db.query(PumpStation).filter(PumpStation.id == device.station_id).first()
    required_skills = _determine_required_skills(device)

    order = MaintenanceOrder(
        device_id=device.id,
        description=f"{device.name}({device.model})运行{device.running_hours}小时，已达保养周期{device.maintenance_cycle_hours}小时，需进行维保",
        required_skills=required_skills,
        status=WorkOrderStatus.PENDING
    )
    db.add(order)
    db.flush()

    team = _find_best_team(db, device, station, required_skills)
    if team:
        order.assigned_team = team.name
        order.status = WorkOrderStatus.ASSIGNED
        team.available = False

    push_work_order(
        db=db,
        target_role="maintenance_team",
        title="维保工单",
        content=f"{station.name if station else ''}{device.name}需维保，已分配至{order.assigned_team or '待分配'}",
        related_id=order.id,
        related_type="maintenance_order"
    )

    db.commit()
    return order


def _determine_required_skills(device: PumpDevice) -> str:
    skills = ["电气维修", "机械维修"]
    if device.rated_power > 100:
        skills.append("高压操作")
    return ",".join(skills)


def _find_best_team(db: Session, device: PumpDevice, station: PumpStation,
                     required_skills: str) -> MaintenanceTeam:
    teams = db.query(MaintenanceTeam).filter(MaintenanceTeam.available == True).all()
    if not teams:
        return None

    required = set(s.strip() for s in required_skills.split(","))
    scored = []
    for team in teams:
        team_skills = set(s.strip() for s in team.skills.split(","))
        skill_match = len(required & team_skills) / len(required) if required else 0

        if station:
            distance = _haversine(team.longitude, team.latitude,
                                  station.longitude, station.latitude)
        else:
            distance = 999

        score = skill_match * 0.7 + max(0, 1 - distance / 50) * 0.3
        scored.append((team, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0][0] if scored and scored[0][1] > 0 else None


def complete_maintenance_order(db: Session, order_id: int) -> MaintenanceOrder:
    order = db.query(MaintenanceOrder).filter(MaintenanceOrder.id == order_id).first()
    if not order:
        raise ValueError("维保工单不存在")

    order.status = WorkOrderStatus.COMPLETED
    order.completed_at = datetime.utcnow()

    device = db.query(PumpDevice).filter(PumpDevice.id == order.device_id).first()
    if device:
        device.last_maintenance_at = datetime.utcnow()
        device.running_hours = 0
        if device.status == DeviceStatus.MAINTENANCE:
            device.status = DeviceStatus.STOPPED

    if order.assigned_team:
        team = db.query(MaintenanceTeam).filter(MaintenanceTeam.name == order.assigned_team).first()
        if team:
            team.available = True

    db.commit()
    return order


def _haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    return R * c
