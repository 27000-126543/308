from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import PumpStation, PumpDevice, PumpDispatch, PumpOperationLog, DeviceStatus
from schemas import (
    PumpStationCreate, PumpStationResponse,
    PumpDeviceCreate, PumpDeviceResponse,
    PumpDispatchResponse, PumpOperationLogCreate, PumpOperationLogResponse
)
from services.maintenance_service import check_maintenance_cycles

router = APIRouter(prefix="/api/pump", tags=["泵站管理"])


@router.post("/stations", response_model=PumpStationResponse)
def create_pump_station(data: PumpStationCreate, db: Session = Depends(get_db)):
    station = PumpStation(**data.model_dump())
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


@router.get("/stations", response_model=list[PumpStationResponse])
def list_pump_stations(district: str = None, db: Session = Depends(get_db)):
    query = db.query(PumpStation)
    if district:
        query = query.filter(PumpStation.district == district)
    return query.all()


@router.get("/stations/{station_id}", response_model=PumpStationResponse)
def get_pump_station(station_id: int, db: Session = Depends(get_db)):
    return db.query(PumpStation).filter(PumpStation.id == station_id).first()


@router.post("/devices", response_model=PumpDeviceResponse)
def create_pump_device(data: PumpDeviceCreate, db: Session = Depends(get_db)):
    device = PumpDevice(**data.model_dump())
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.get("/devices", response_model=list[PumpDeviceResponse])
def list_pump_devices(station_id: int = None, db: Session = Depends(get_db)):
    query = db.query(PumpDevice)
    if station_id:
        query = query.filter(PumpDevice.station_id == station_id)
    return query.all()


@router.post("/operation-logs", response_model=PumpOperationLogResponse)
def create_operation_log(data: PumpOperationLogCreate, db: Session = Depends(get_db)):
    from datetime import datetime
    log = PumpOperationLog(**data.model_dump())
    db.add(log)

    station = db.query(PumpStation).filter(PumpStation.id == data.station_id).first()
    if station:
        station.current_discharge += data.discharge_volume
        devices = db.query(PumpDevice).filter(PumpDevice.station_id == data.station_id).all()
        for d in devices:
            d.running_hours += data.running_hours

    check_maintenance_cycles(db)

    db.commit()
    db.refresh(log)
    return log


@router.get("/dispatches", response_model=list[PumpDispatchResponse])
def list_dispatches(warning_id: int = None, db: Session = Depends(get_db)):
    query = db.query(PumpDispatch)
    if warning_id:
        query = query.filter(PumpDispatch.warning_id == warning_id)
    return query.order_by(PumpDispatch.issued_at.desc()).all()


@router.put("/dispatches/{dispatch_id}/acknowledge", response_model=PumpDispatchResponse)
def acknowledge_dispatch(dispatch_id: int, db: Session = Depends(get_db)):
    from datetime import datetime
    dispatch = db.query(PumpDispatch).filter(PumpDispatch.id == dispatch_id).first()
    if not dispatch:
        return None
    dispatch.acknowledged_at = datetime.utcnow()
    dispatch.status = "acknowledged"
    db.commit()
    db.refresh(dispatch)
    return dispatch
