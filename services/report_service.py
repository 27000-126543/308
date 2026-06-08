from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from models import (
    DailyReport, PumpStation, PumpOperationLog,
    ResourceAllocation, ResourceAllocationPlan, MaterialType,
    AllocationStatus, InspectionOrder, WorkOrderStatus, Warning
)


def generate_daily_report(db: Session, report_date: date = None):
    if not report_date:
        report_date = date.today() - timedelta(days=1)

    start = datetime.combine(report_date, datetime.min.time())
    end = datetime.combine(report_date, datetime.max.time())

    stations = db.query(PumpStation).all()
    districts = set(s.district for s in stations)

    if not districts:
        districts = set()

    alloc_plans = db.query(ResourceAllocationPlan).filter(
        ResourceAllocationPlan.approved_at.between(start, end)
    ).all()
    for plan in alloc_plans:
        districts.add(plan.district)

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

        avg_response_time = 0
        warnings_in_district = db.query(Warning).filter(
            Warning.district == district,
            Warning.created_at.between(start, end)
        ).all()

        if warnings_in_district:
            dispatch_times = []
            for w in warnings_in_district:
                for d in w.dispatches:
                    if d.acknowledged_at:
                        dispatch_times.append((d.issued_at, d.acknowledged_at))
            if dispatch_times:
                response_times = [(ack - issued).total_seconds() / 60
                                  for issued, ack in dispatch_times]
                avg_response_time = sum(response_times) / len(response_times)

        material_consumption = {}
        material_shipped = {}
        material_arrived = {}

        for mat_type in MaterialType:
            allocs = db.query(ResourceAllocation).join(
                ResourceAllocationPlan,
                ResourceAllocation.plan_id == ResourceAllocationPlan.id
            ).filter(
                ResourceAllocation.material_type == mat_type,
                ResourceAllocationPlan.district == district,
                ResourceAllocationPlan.approved_at.between(start, end)
            ).all()

            total_consumed = sum(a.consumed_quantity for a in allocs)
            total_shipped = sum(a.quantity for a in allocs if a.status in (
                AllocationStatus.SHIPPED, AllocationStatus.ARRIVED, AllocationStatus.CONSUMED
            ))
            total_arrived = sum(a.quantity for a in allocs if a.status in (
                AllocationStatus.ARRIVED, AllocationStatus.CONSUMED
            ))

            material_consumption[mat_type.value] = total_consumed
            material_shipped[mat_type.value] = total_shipped
            material_arrived[mat_type.value] = total_arrived

        report = DailyReport(
            report_date=report_date,
            district=district,
            total_discharge=total_discharge,
            total_energy=total_energy,
            avg_response_time=avg_response_time,
            material_consumption=material_consumption,
            material_shipped=material_shipped,
            material_arrived=material_arrived,
            pump_stats=pump_stats,
            generated_at=datetime.utcnow()
        )
        db.add(report)

    db.commit()


def export_report(db: Session, start_date: date = None, end_date: date = None, district: str = None):
    query = db.query(DailyReport)
    if start_date:
        query = query.filter(DailyReport.report_date >= start_date)
    if end_date:
        query = query.filter(DailyReport.report_date <= end_date)
    if district:
        query = query.filter(DailyReport.district == district)
    return query.order_by(DailyReport.report_date.desc(), DailyReport.district).all()


def export_report_to_excel(db: Session, start_date: date = None, end_date: date = None, district: str = None):
    reports = export_report(db, start_date, end_date, district)
    if not reports:
        return None

    try:
        from openpyxl import Workbook
    except ImportError:
        return None

    wb = Workbook()
    ws = wb.active
    ws.title = "排涝运行报告"
    headers = [
        "日期", "区域", "总排水量(m³)", "总能耗(kWh)", "平均响应时间(分钟)",
        "物资消耗", "物资出库", "物资到达", "泵站统计"
    ]
    ws.append(headers)

    for r in reports:
        mat_consumed = "; ".join(f"{k}:{v}" for k, v in (r.material_consumption or {}).items())
        mat_shipped = "; ".join(f"{k}:{v}" for k, v in (r.material_shipped or {}).items())
        mat_arrived = "; ".join(f"{k}:{v}" for k, v in (r.material_arrived or {}).items())
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
            mat_consumed,
            mat_shipped,
            mat_arrived,
            pump_str
        ])

    from io import BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
