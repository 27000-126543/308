from datetime import date
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
from models import HiddenDanger, WaterloggingEvent, ReplenishmentRequest, ApprovalReminder
from schemas import (
    HiddenDangerResponse, WaterloggingEventCreate, WaterloggingEventResponse,
    ReplenishmentRequestResponse, ApprovalReminderResponse, DailyReportResponse
)
from services.risk_service import record_waterlogging_event
from services.replenishment_service import check_approval_timeouts
from services.report_service import generate_daily_report, export_report, export_report_to_excel

router = APIRouter(prefix="/api/system", tags=["系统管理"])


@router.get("/hidden-dangers", response_model=list[HiddenDangerResponse])
def list_hidden_dangers(district: str = None, is_high_risk: bool = None,
                        db: Session = Depends(get_db)):
    query = db.query(HiddenDanger)
    if district:
        query = query.filter(HiddenDanger.district == district)
    if is_high_risk is not None:
        query = query.filter(HiddenDanger.is_high_risk == is_high_risk)
    return query.order_by(HiddenDanger.updated_at.desc()).all()


@router.post("/waterlogging-events", response_model=WaterloggingEventResponse)
def create_waterlogging_event(data: WaterloggingEventCreate, db: Session = Depends(get_db)):
    return record_waterlogging_event(
        db=db,
        location=data.location,
        district=data.district,
        longitude=data.longitude,
        latitude=data.latitude,
        water_depth=data.water_depth,
        warning_id=data.warning_id
    )


@router.get("/waterlogging-events", response_model=list[WaterloggingEventResponse])
def list_waterlogging_events(district: str = None, limit: int = 100,
                             db: Session = Depends(get_db)):
    query = db.query(WaterloggingEvent)
    if district:
        query = query.filter(WaterloggingEvent.district == district)
    return query.order_by(WaterloggingEvent.recorded_at.desc()).limit(limit).all()


@router.get("/replenishment-requests", response_model=list[ReplenishmentRequestResponse])
def list_replenishment_requests(db: Session = Depends(get_db)):
    return db.query(ReplenishmentRequest).order_by(
        ReplenishmentRequest.created_at.desc()
    ).all()


@router.post("/check-approval-timeouts")
def check_timeouts(db: Session = Depends(get_db)):
    check_approval_timeouts(db)
    return {"message": "审批超时检查完成"}


@router.get("/approval-reminders", response_model=list[ApprovalReminderResponse])
def list_approval_reminders(request_id: int = None, level: str = None,
                            escalated: bool = None, db: Session = Depends(get_db)):
    query = db.query(ApprovalReminder)
    if request_id:
        query = query.filter(ApprovalReminder.request_id == request_id)
    if level:
        query = query.filter(ApprovalReminder.level == level)
    if escalated is not None:
        query = query.filter(ApprovalReminder.escalated == escalated)
    return query.order_by(ApprovalReminder.created_at.desc()).all()


@router.post("/generate-daily-report")
def generate_report(report_date: date = None, db: Session = Depends(get_db)):
    generate_daily_report(db, report_date)
    return {"message": f"日报生成完成: {report_date or date.today()}"}


@router.get("/daily-reports", response_model=list[DailyReportResponse])
def get_reports(start_date: date = None, end_date: date = None,
                district: str = None, db: Session = Depends(get_db)):
    return export_report(db, start_date, end_date, district)


@router.get("/daily-reports/export")
def export_report_excel(start_date: date = None, end_date: date = None,
                        district: str = None, db: Session = Depends(get_db)):
    output = export_report_to_excel(db, start_date, end_date, district)
    if not output:
        return {"message": "无数据可导出"}
    date_range = f"{start_date or 'start'}_to_{end_date or 'end'}"
    district_suffix = f"_{district}" if district else "_all_districts"
    filename = f"flood_report_{date_range}{district_suffix}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
