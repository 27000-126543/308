from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import (
    DailyReport, PumpStation, PumpOperationLog,
    ResourceAllocation, MaterialType, InspectionOrder,
    InspectionReport, WorkOrderStatus, Warning
)
import json


def generate_daily_report(db: Session, report_date: date = None):
    if not report_date:
        report_date = date.today() - timedelta(days=1)

    start = datetime.combine(report_date, datetime.min.time())
    end = datetime.combine(report_date, datetime.max.time())

    stations = db.query(PumpStation).all()
    districts = set(s.district for s in stations)

    for district in districts:
        existing = db.query(DailyReport).filter(
            DailyReport.report_date == report_date,
            DailyReport.district == district
        ).first()
        if existing:
            continue

        district_stations = [s for s in stations if s.district == district]

        total_discharge = 0
        total_energy = 0
        pump_stats = []

        for station in district_stations:
            logs = db.query(PumpOperationLog).filter(
                PumpOperationLog.station_id == station.id,
                PumpOperationLog.recorded_at.between(start, end)
            ).all()

            station_discharge = sum(log.discharge_volume for log in logs)
            station_energy = sum(log.energy_consumption for log in logs)
            total_discharge += station_discharge
            total_energy += station_energy

            pump_stats.append({
                "station_name": station.name,
                "discharge_volume": station_discharge,
                "energy_consumption": station_energy,
                "log_count": len(logs)
            })

        warnings_in_district = db.query(Warning).filter(
            Warning.district == district,
            Warning.created_at.between(start, end)
        ).all()

        first_warning_time = None
        last_response_time = None
        if warnings_in_district:
            first_warning_time = min(w.created_at for w in warnings_in_district)
            dispatches_for_warnings = []
            for w in warnings_in_district:
                for d in w.dispatches:
                    if d.acknowledged_at:
                        dispatches_for_warnings.append((d.issued_at, d.acknowledged_at))
            if dispatches_for_warnings:
                response_times = [(ack - issued).total_seconds() / 60
                                  for issued, ack in dispatches_for_warnings]
                last_response_time = sum(response_times) / len(response_times) if response_times else 0

        orders = db.query(InspectionOrder).filter(
            InspectionOrder.district == district,
            InspectionOrder.created_at.between(start, end)
        ).all()

        completed_orders = [o for o in orders if o.status == WorkOrderStatus.COMPLETED]
        avg_response_time = last_response_time if last_response_time else 0

        material_consumption = {}
        for mat_type in MaterialType:
            allocs = db.query(ResourceAllocation).join(
                ResourceAllocation.plan
            ).filter(
                ResourceAllocation.material_type == mat_type,
                ResourceAllocation.locked == True
            ).all()
            total_used = sum(a.quantity for a in allocs)
            material_consumption[mat_type.value] = total_used

        report = DailyReport(
            report_date=report_date,
            district=district,
            total_discharge=total_discharge,
            total_energy=total_energy,
            avg_response_time=avg_response_time,
            material_consumption=material_consumption,
            pump_stats=pump_stats,
            generated_at=datetime.utcnow()
        )
        db.add(report)

    db.commit()


def export_report(db: Session, report_date: date = None, district: str = None):
    query = db.query(DailyReport)
    if report_date:
        query = query.filter(DailyReport.report_date == report_date)
    if district:
        query = query.filter(DailyReport.district == district)

    return query.order_by(DailyReport.report_date.desc()).all()


def export_report_to_excel(db: Session, report_date: date = None, district: str = None):
    reports = export_report(db, report_date, district)
    if not reports:
        return None

    try:
        from openpyxl import Workbook
    except ImportError:
        return None

    wb = Workbook()
    ws = wb.active
    ws.title = "排涝运行报告"
    headers = ["日期", "区域", "总排水量(m³)", "总能耗(kWh)", "平均响应时间(分钟)", "物资消耗", "泵站统计"]
    ws.append(headers)

    for r in reports:
        mat_str = "; ".join(f"{k}:{v}" for k, v in (r.material_consumption or {}).items())
        pump_str = "; ".join(
            f"{p.get('station_name', '')}排水{p.get('discharge_volume', 0)}m³"
            for p in (r.pump_stats or [])
        )
        ws.append([
            str(r.report_date),
            r.district,
            r.total_discharge,
            r.total_energy,
            r.avg_response_time,
            mat_str,
            pump_str
        ])

    from io import BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
