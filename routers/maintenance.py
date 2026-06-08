from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import (
    MaintenanceOrder, MaintenanceTeam, PumpDevice, WorkOrderStatus
)
from schemas import (
    MaintenanceOrderCreate, MaintenanceOrderResponse,
    MaintenanceTeamCreate, MaintenanceTeamResponse
)
from services.maintenance_service import (
    check_maintenance_cycles, complete_maintenance_order
)

router = APIRouter(prefix="/api/maintenance", tags=["维保管理"])


@router.post("/check-cycles")
def check_cycles(db: Session = Depends(get_db)):
    check_maintenance_cycles(db)
    return {"message": "维保周期检查完成"}


@router.get("/orders", response_model=list[MaintenanceOrderResponse])
def list_maintenance_orders(status: WorkOrderStatus = None, db: Session = Depends(get_db)):
    query = db.query(MaintenanceOrder)
    if status:
        query = query.filter(MaintenanceOrder.status == status)
    return query.order_by(MaintenanceOrder.created_at.desc()).all()


@router.get("/orders/{order_id}", response_model=MaintenanceOrderResponse)
def get_maintenance_order(order_id: int, db: Session = Depends(get_db)):
    return db.query(MaintenanceOrder).filter(MaintenanceOrder.id == order_id).first()


@router.put("/orders/{order_id}/complete", response_model=MaintenanceOrderResponse)
def complete_order(order_id: int, db: Session = Depends(get_db)):
    return complete_maintenance_order(db, order_id)


@router.post("/teams", response_model=MaintenanceTeamResponse)
def create_maintenance_team(data: MaintenanceTeamCreate, db: Session = Depends(get_db)):
    team = MaintenanceTeam(**data.model_dump())
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


@router.get("/teams", response_model=list[MaintenanceTeamResponse])
def list_maintenance_teams(district: str = None, db: Session = Depends(get_db)):
    query = db.query(MaintenanceTeam)
    if district:
        query = query.filter(MaintenanceTeam.district == district)
    return query.all()


@router.get("/devices", response_model=list[dict])
def list_devices_with_maintenance_status(station_id: int = None, db: Session = Depends(get_db)):
    query = db.query(PumpDevice)
    if station_id:
        query = query.filter(PumpDevice.station_id == station_id)
    devices = query.all()
    result = []
    for d in devices:
        needs_maintenance = d.running_hours >= d.maintenance_cycle_hours
        result.append({
            "id": d.id,
            "name": d.name,
            "model": d.model,
            "station_id": d.station_id,
            "running_hours": d.running_hours,
            "maintenance_cycle_hours": d.maintenance_cycle_hours,
            "needs_maintenance": needs_maintenance,
            "status": d.status.value
        })
    return result
