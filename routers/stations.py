from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import RainStation, WaterLevelStation, RainRecord, WaterLevelRecord
from schemas import (
    RainStationCreate, RainStationResponse,
    WaterLevelStationCreate, WaterLevelStationResponse,
    RainRecordCreate, RainRecordResponse,
    WaterLevelRecordCreate, WaterLevelRecordResponse,
)
from services.risk_service import process_rain_data, process_water_level_data

router = APIRouter(prefix="/api/stations", tags=["监测站管理"])


@router.post("/rain", response_model=RainStationResponse)
def create_rain_station(data: RainStationCreate, db: Session = Depends(get_db)):
    station = RainStation(**data.model_dump())
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


@router.get("/rain", response_model=list[RainStationResponse])
def list_rain_stations(district: str = None, db: Session = Depends(get_db)):
    query = db.query(RainStation)
    if district:
        query = query.filter(RainStation.district == district)
    return query.all()


@router.get("/rain/{station_id}", response_model=RainStationResponse)
def get_rain_station(station_id: int, db: Session = Depends(get_db)):
    return db.query(RainStation).filter(RainStation.id == station_id).first()


@router.post("/water-level", response_model=WaterLevelStationResponse)
def create_water_level_station(data: WaterLevelStationCreate, db: Session = Depends(get_db)):
    station = WaterLevelStation(**data.model_dump())
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


@router.get("/water-level", response_model=list[WaterLevelStationResponse])
def list_water_level_stations(district: str = None, db: Session = Depends(get_db)):
    query = db.query(WaterLevelStation)
    if district:
        query = query.filter(WaterLevelStation.district == district)
    return query.all()


@router.post("/rain-data", response_model=RainRecordResponse)
def upload_rain_data(data: RainRecordCreate, db: Session = Depends(get_db)):
    return process_rain_data(
        db=db,
        station_id=data.station_id,
        rainfall_1h=data.rainfall_1h,
        rainfall_3h=data.rainfall_3h,
        rainfall_6h=data.rainfall_6h,
        rainfall_24h=data.rainfall_24h
    )


@router.post("/water-level-data", response_model=WaterLevelRecordResponse)
def upload_water_level_data(data: WaterLevelRecordCreate, db: Session = Depends(get_db)):
    return process_water_level_data(
        db=db,
        station_id=data.station_id,
        water_level=data.water_level,
        flow_rate=data.flow_rate
    )


@router.get("/rain-data/{station_id}", response_model=list[RainRecordResponse])
def get_rain_records(station_id: int, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(RainRecord).filter(
        RainRecord.station_id == station_id
    ).order_by(RainRecord.recorded_at.desc()).limit(limit).all()


@router.get("/water-level-data/{station_id}", response_model=list[WaterLevelRecordResponse])
def get_water_level_records(station_id: int, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(WaterLevelRecord).filter(
        WaterLevelRecord.station_id == station_id
    ).order_by(WaterLevelRecord.recorded_at.desc()).limit(limit).all()
