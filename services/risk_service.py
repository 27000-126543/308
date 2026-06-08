import math
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models import (
    RainRecord, WaterLevelRecord, RainStation, WaterLevelStation,
    PipeNetwork, GroundElevation, Warning, WarningStatus,
    PumpStation, PumpDispatch, RiskLevel, DeviceStatus,
    WaterloggingEvent, HiddenDanger
)
from services.push_service import push_warning, push_dispatch


def calculate_risk_level(rainfall_intensity: float, pipe_usage_ratio: float, elevation_risk: float) -> RiskLevel:
    score = 0
    if rainfall_intensity >= 50:
        score += 4
    elif rainfall_intensity >= 25:
        score += 3
    elif rainfall_intensity >= 10:
        score += 2
    else:
        score += 1

    if pipe_usage_ratio >= 0.9:
        score += 4
    elif pipe_usage_ratio >= 0.7:
        score += 3
    elif pipe_usage_ratio >= 0.5:
        score += 2
    else:
        score += 1

    score += int(elevation_risk)

    if score >= 10:
        return RiskLevel.RED
    elif score >= 7:
        return RiskLevel.ORANGE
    elif score >= 5:
        return RiskLevel.YELLOW
    else:
        return RiskLevel.BLUE


def process_rain_data(db: Session, station_id: int, rainfall_1h: float, rainfall_3h: float = 0,
                      rainfall_6h: float = 0, rainfall_24h: float = 0) -> RainRecord:
    record = RainRecord(
        station_id=station_id,
        rainfall_1h=rainfall_1h,
        rainfall_3h=rainfall_3h,
        rainfall_6h=rainfall_6h,
        rainfall_24h=rainfall_24h
    )
    db.add(record)

    station = db.query(RainStation).filter(RainStation.id == station_id).first()
    if not station:
        db.commit()
        return record

    pipe = db.query(PipeNetwork).filter(PipeNetwork.district == station.district).first()
    pipe_usage = pipe.current_usage / pipe.total_capacity if pipe else 0.5

    ground = db.query(GroundElevation).filter(GroundElevation.district == station.district).first()
    elevation_risk = 0
    if ground and ground.elevation < 5:
        elevation_risk = 3
    elif ground and ground.elevation < 10:
        elevation_risk = 2
    else:
        elevation_risk = 1

    risk_level = calculate_risk_level(rainfall_1h, pipe_usage, elevation_risk)

    if risk_level in (RiskLevel.YELLOW, RiskLevel.ORANGE, RiskLevel.RED):
        active_warning = db.query(Warning).filter(
            Warning.district == station.district,
            Warning.status == WarningStatus.ACTIVE
        ).first()

        if active_warning:
            active_warning.risk_level = risk_level
            active_warning.rainfall_intensity = rainfall_1h
            active_warning.pipe_usage_ratio = pipe_usage
            active_warning.elevation_risk = elevation_risk
            warning = active_warning
        else:
            warning = Warning(
                district=station.district,
                risk_level=risk_level,
                rainfall_intensity=rainfall_1h,
                pipe_usage_ratio=pipe_usage,
                elevation_risk=elevation_risk,
                description=f"{station.district}降雨强度{rainfall_1h}mm/h，风险等级{risk_level.value}"
            )
            db.add(warning)

        db.flush()

        push_warning(
            db=db,
            target_role="headquarters",
            title=f"内涝预警-{risk_level.value}",
            content=f"{station.district}降雨强度{rainfall_1h}mm/h，管网使用率{pipe_usage:.1%}，风险等级{risk_level.value}",
            related_id=warning.id,
            related_type="warning"
        )

        _trigger_pump_pre_dispatch(db, warning, station.district)

    db.commit()
    return record


def process_water_level_data(db: Session, station_id: int, water_level: float, flow_rate: float = 0) -> WaterLevelRecord:
    record = WaterLevelRecord(
        station_id=station_id,
        water_level=water_level,
        flow_rate=flow_rate
    )
    db.add(record)

    station = db.query(WaterLevelStation).filter(WaterLevelStation.id == station_id).first()
    if station and water_level >= station.warning_level:
        pipe = db.query(PipeNetwork).filter(PipeNetwork.district == station.district).first()
        pipe_usage = pipe.current_usage / pipe.total_capacity if pipe else 0.5

        ground = db.query(GroundElevation).filter(GroundElevation.district == station.district).first()
        elevation_risk = 0
        if ground and ground.elevation < 5:
            elevation_risk = 3
        elif ground and ground.elevation < 10:
            elevation_risk = 2
        else:
            elevation_risk = 1

        risk_level = calculate_risk_level(station.warning_level * 0.8, pipe_usage, elevation_risk)

        active_warning = db.query(Warning).filter(
            Warning.district == station.district,
            Warning.status == WarningStatus.ACTIVE
        ).first()

        if active_warning:
            active_warning.risk_level = risk_level
            warning = active_warning
        else:
            warning = Warning(
                district=station.district,
                risk_level=risk_level,
                rainfall_intensity=station.warning_level * 0.8,
                pipe_usage_ratio=pipe_usage,
                elevation_risk=elevation_risk,
                description=f"{station.district}水位{water_level}m超警戒水位{station.warning_level}m"
            )
            db.add(warning)

        db.flush()

        push_warning(
            db=db,
            target_role="headquarters",
            title=f"水位预警-{risk_level.value}",
        content=f"{station.district}水位{water_level}m超警戒水位{station.warning_level}m",
            related_id=warning.id,
            related_type="warning"
        )

        _trigger_pump_pre_dispatch(db, warning, station.district)

    db.commit()
    return record


def _trigger_pump_pre_dispatch(db: Session, warning: Warning, district: str):
    pumps = db.query(PumpStation).filter(
        PumpStation.district == district,
        PumpStation.status.in_([DeviceStatus.RUNNING, DeviceStatus.STOPPED])
    ).all()

    for pump in pumps:
        existing = db.query(PumpDispatch).filter(
            PumpDispatch.warning_id == warning.id,
            PumpDispatch.station_id == pump.id
        ).first()
        if existing:
            continue

        target = pump.design_capacity * (0.8 if warning.risk_level == RiskLevel.YELLOW else 1.0)
        dispatch = PumpDispatch(
            warning_id=warning.id,
            station_id=pump.id,
            target_discharge=target,
            instruction=f"预排指令：因{district}{warning.risk_level.value}色预警，请将排涝量调整至{target}m³/h",
            status="issued"
        )
        db.add(dispatch)

        push_dispatch(
            db=db,
            target_role="pump_duty",
            title="泵站预排指令",
            content=f"{pump.name}：{dispatch.instruction}",
            related_id=dispatch.id,
            related_type="dispatch"
        )

    db.flush()


def record_waterlogging_event(db: Session, location: str, district: str,
                               longitude: float, latitude: float,
                               water_depth: float, warning_id: int = None):
    event = WaterloggingEvent(
        location=location,
        district=district,
        longitude=longitude,
        latitude=latitude,
        water_depth=water_depth,
        warning_id=warning_id
    )
    db.add(event)
    db.flush()

    _check_repeated_waterlogging(db, location, district, longitude, latitude)

    db.commit()
    return event


def _check_repeated_waterlogging(db: Session, location: str, district: str,
                                  longitude: float, latitude: float):
    threshold_date = datetime.utcnow() - timedelta(days=30)

    nearby_events = db.query(WaterloggingEvent).filter(
        WaterloggingEvent.district == district,
        WaterloggingEvent.recorded_at >= threshold_date
    ).all()

    matching = [e for e in nearby_events
                if _calculate_distance(e.longitude, e.latitude, longitude, latitude) < 0.5]

    if len(matching) >= 2:
        danger = db.query(HiddenDanger).filter(
            HiddenDanger.district == district,
            HiddenDanger.is_high_risk == True
        ).filter(
            _nearby_filter(HiddenDanger, longitude, latitude)
        ).first()

        if not danger:
            danger = HiddenDanger(
                location=location,
                district=district,
                longitude=longitude,
                latitude=latitude,
                waterlogging_count=len(matching),
                last_waterlogging_at=datetime.utcnow(),
                is_high_risk=True,
                renovation_suggestion=f"该点位30天内已发生{len(matching)}次积水，建议进行管网改造或增设排水设施",
                pushed_to_planning=True,
                in_annual_plan=False
            )
            db.add(danger)
        else:
            danger.waterlogging_count = len(matching)
            danger.last_waterlogging_at = datetime.utcnow()
            danger.renovation_suggestion = f"该点位30天内已发生{len(matching)}次积水，建议进行管网改造或增设排水设施"

        from services.push_service import push_message
        push_message(
            db=db,
            target_role="planning_dept",
            category="work_order",
            title="高风险隐患点通知",
            content=f"{district}{location}30天内积水{len(matching)}次，已标记高风险，请纳入改造计划",
            related_id=danger.id if danger.id else 0,
            related_type="hidden_danger"
        )


def _calculate_distance(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def _nearby_filter(model, longitude: float, latitude: float):
    from sqlalchemy import and_
    return and_(
        model.longitude.between(longitude - 0.01, longitude + 0.01),
        model.latitude.between(latitude - 0.01, latitude + 0.01)
    )
