from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import Warning, WarningStatus, RiskLevel
from schemas import WarningResponse, RiskCalculationRequest, RiskCalculationResponse
from services.risk_service import calculate_risk_level
from services.dispatch_service import generate_resource_plan

router = APIRouter(prefix="/api/warnings", tags=["预警管理"])


@router.get("", response_model=list[WarningResponse])
def list_warnings(district: str = None, risk_level: RiskLevel = None,
                  status: WarningStatus = None, db: Session = Depends(get_db)):
    query = db.query(Warning)
    if district:
        query = query.filter(Warning.district == district)
    if risk_level:
        query = query.filter(Warning.risk_level == risk_level)
    if status:
        query = query.filter(Warning.status == status)
    return query.order_by(Warning.created_at.desc()).all()


@router.get("/{warning_id}", response_model=WarningResponse)
def get_warning(warning_id: int, db: Session = Depends(get_db)):
    return db.query(Warning).filter(Warning.id == warning_id).first()


@router.put("/{warning_id}/lift", response_model=WarningResponse)
def lift_warning(warning_id: int, db: Session = Depends(get_db)):
    from datetime import datetime
    warning = db.query(Warning).filter(Warning.id == warning_id).first()
    if not warning:
        return None
    warning.status = WarningStatus.LIFTED
    warning.lifted_at = datetime.utcnow()
    db.commit()
    db.refresh(warning)
    return warning


@router.post("/calculate-risk", response_model=RiskCalculationResponse)
def calculate_risk(req: RiskCalculationRequest, db: Session = Depends(get_db)):
    risk_level = calculate_risk_level(
        req.rainfall_intensity,
        req.pipe_usage_ratio,
        req.elevation_risk
    )
    warning = Warning(
        district=req.district,
        risk_level=risk_level,
        rainfall_intensity=req.rainfall_intensity,
        pipe_usage_ratio=req.pipe_usage_ratio,
        elevation_risk=req.elevation_risk
    )
    db.add(warning)
    db.commit()
    db.refresh(warning)
    return warning


@router.post("/{warning_id}/trigger-resource-plan")
def trigger_resource_plan(warning_id: int, db: Session = Depends(get_db)):
    warning = db.query(Warning).filter(Warning.id == warning_id).first()
    if not warning:
        return {"error": "预警不存在"}
    plan = generate_resource_plan(db, warning)
    if plan:
        return {"message": "资源调配方案已生成", "plan_id": plan.id}
    return {"message": "预警等级未达资源调配阈值"}
