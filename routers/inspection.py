from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
from database import get_db
from models import (
    InspectionOrder, InspectionReport, TrafficControlPlan,
    GuideScreen, WorkOrderStatus, ApprovalStatus
)
from schemas import (
    InspectionOrderResponse, InspectionReportResponse,
    TrafficControlPlanResponse, GuideScreenUpdate, GuideScreenResponse
)
from services.inspection_service import (
    create_inspection_order, submit_inspection_report, approve_traffic_control
)

router = APIRouter(prefix="/api/inspection", tags=["巡查与交通管制"])


@router.post("/orders", response_model=InspectionOrderResponse)
def create_order(warning_id: int, inspector_name: str, district: str,
                 location: str, longitude: float, latitude: float,
                 db: Session = Depends(get_db)):
    return create_inspection_order(
        db=db, warning_id=warning_id, inspector_name=inspector_name,
        district=district, location=location, longitude=longitude, latitude=latitude
    )


@router.get("/orders", response_model=list[InspectionOrderResponse])
def list_orders(district: str = None, status: WorkOrderStatus = None,
                db: Session = Depends(get_db)):
    query = db.query(InspectionOrder)
    if district:
        query = query.filter(InspectionOrder.district == district)
    if status:
        query = query.filter(InspectionOrder.status == status)
    return query.order_by(InspectionOrder.created_at.desc()).all()


@router.get("/orders/{order_id}", response_model=InspectionOrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    return db.query(InspectionOrder).filter(InspectionOrder.id == order_id).first()


@router.post("/reports", response_model=InspectionReportResponse)
def submit_report(order_id: int, water_depth: float,
                  photo_url: str = None, description: str = "",
                  db: Session = Depends(get_db)):
    return submit_inspection_report(
        db=db, order_id=order_id, water_depth=water_depth,
        photo_url=photo_url, description=description
    )


@router.get("/reports", response_model=list[InspectionReportResponse])
def list_reports(order_id: int = None, db: Session = Depends(get_db)):
    query = db.query(InspectionReport)
    if order_id:
        query = query.filter(InspectionReport.order_id == order_id)
    return query.order_by(InspectionReport.reported_at.desc()).all()


@router.get("/traffic-plans", response_model=list[TrafficControlPlanResponse])
def list_traffic_plans(district: str = None, approval_status: ApprovalStatus = None,
                       db: Session = Depends(get_db)):
    query = db.query(TrafficControlPlan)
    if district:
        query = query.filter(TrafficControlPlan.district == district)
    if approval_status:
        query = query.filter(TrafficControlPlan.approval_status == approval_status)
    return query.order_by(TrafficControlPlan.created_at.desc()).all()


@router.put("/traffic-plans/{plan_id}/approve", response_model=TrafficControlPlanResponse)
def approve_traffic(plan_id: int, approver: str, db: Session = Depends(get_db)):
    return approve_traffic_control(db, plan_id, approver)


@router.get("/guide-screens", response_model=list[GuideScreenResponse])
def list_guide_screens(district: str = None, db: Session = Depends(get_db)):
    query = db.query(GuideScreen)
    if district:
        query = query.filter(GuideScreen.district == district)
    return query.all()


@router.post("/guide-screens", response_model=GuideScreenResponse)
def create_guide_screen(code: str, location: str, district: str,
                        longitude: float, latitude: float,
                        current_content: str = "",
                        db: Session = Depends(get_db)):
    from datetime import datetime
    screen = GuideScreen(
        code=code, location=location, district=district,
        longitude=longitude, latitude=latitude,
        current_content=current_content
    )
    db.add(screen)
    db.commit()
    db.refresh(screen)
    return screen


@router.put("/guide-screens/{screen_id}", response_model=GuideScreenResponse)
def update_guide_screen(screen_id: int, data: GuideScreenUpdate,
                        db: Session = Depends(get_db)):
    from datetime import datetime
    screen = db.query(GuideScreen).filter(GuideScreen.id == screen_id).first()
    if not screen:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(screen, key, value)
    screen.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(screen)
    return screen
