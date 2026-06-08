from __future__ import annotations
from datetime import datetime, date
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict
from models import (
    RiskLevel, ApprovalStatus, WorkOrderStatus, WarningStatus,
    MaterialType, DeviceStatus, TrafficControlType, AllocationStatus,
)


class RainStationCreate(BaseModel):
    name: str
    code: str
    district: str
    longitude: float
    latitude: float
    elevation: float


class RainStationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    district: str
    longitude: float
    latitude: float
    elevation: float
    created_at: datetime


class WaterLevelStationCreate(BaseModel):
    name: str
    code: str
    district: str
    longitude: float
    latitude: float
    warning_level: float
    guarantee_level: float


class WaterLevelStationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    district: str
    longitude: float
    latitude: float
    warning_level: float
    guarantee_level: float
    created_at: datetime


class RainRecordCreate(BaseModel):
    station_id: int
    rainfall_1h: float
    rainfall_3h: float = 0
    rainfall_6h: float = 0
    rainfall_24h: float = 0


class RainRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    station_id: int
    rainfall_1h: float
    rainfall_3h: float
    rainfall_6h: float
    rainfall_24h: float
    recorded_at: datetime


class WaterLevelRecordCreate(BaseModel):
    station_id: int
    water_level: float
    flow_rate: float = 0


class WaterLevelRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    station_id: int
    water_level: float
    flow_rate: float
    recorded_at: datetime


class PipeNetworkCreate(BaseModel):
    district: str
    total_capacity: float
    current_usage: float = 0


class PipeNetworkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    district: str
    total_capacity: float
    current_usage: float
    updated_at: datetime


class GroundElevationCreate(BaseModel):
    district: str
    area_name: str
    longitude: float
    latitude: float
    elevation: float
    drainage_grade: str = "P3"


class GroundElevationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    district: str
    area_name: str
    longitude: float
    latitude: float
    elevation: float
    drainage_grade: str


class WarningCreate(BaseModel):
    district: str
    risk_level: RiskLevel
    rainfall_intensity: float
    pipe_usage_ratio: float
    elevation_risk: float = 0
    status: WarningStatus = WarningStatus.ACTIVE
    description: str = ""


class WarningResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    district: str
    risk_level: RiskLevel
    rainfall_intensity: float
    pipe_usage_ratio: float
    elevation_risk: float
    status: WarningStatus
    description: str
    created_at: datetime
    lifted_at: Optional[datetime] = None


class PumpStationCreate(BaseModel):
    name: str
    code: str
    district: str
    longitude: float
    latitude: float
    design_capacity: float
    current_discharge: float = 0
    status: DeviceStatus = DeviceStatus.STOPPED


class PumpStationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    district: str
    longitude: float
    latitude: float
    design_capacity: float
    current_discharge: float
    status: DeviceStatus
    created_at: datetime


class PumpDeviceCreate(BaseModel):
    station_id: int
    name: str
    model: str
    rated_power: float
    running_hours: float = 0
    maintenance_cycle_hours: float = 2000
    last_maintenance_at: Optional[datetime] = None
    status: DeviceStatus = DeviceStatus.STOPPED


class PumpDeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    station_id: int
    name: str
    model: str
    rated_power: float
    running_hours: float
    maintenance_cycle_hours: float
    last_maintenance_at: Optional[datetime] = None
    status: DeviceStatus


class PumpDispatchCreate(BaseModel):
    warning_id: int
    station_id: int
    target_discharge: float
    instruction: str = ""
    status: str = "issued"


class PumpDispatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    warning_id: int
    station_id: int
    target_discharge: float
    instruction: str
    status: str
    issued_at: datetime
    acknowledged_at: Optional[datetime] = None


class PumpOperationLogCreate(BaseModel):
    station_id: int
    discharge_volume: float = 0
    energy_consumption: float = 0
    running_hours: float = 0


class PumpOperationLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    station_id: int
    discharge_volume: float
    energy_consumption: float
    running_hours: float
    recorded_at: datetime


class WarehouseCreate(BaseModel):
    name: str
    district: str
    longitude: float
    latitude: float


class WarehouseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    district: str
    longitude: float
    latitude: float
    created_at: datetime


class MaterialInventoryCreate(BaseModel):
    warehouse_id: int
    material_type: MaterialType
    quantity: int
    safety_stock: int
    locked_quantity: int = 0


class MaterialInventoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    warehouse_id: int
    material_type: MaterialType
    quantity: int
    safety_stock: int
    locked_quantity: int
    updated_at: datetime


class ResourceAllocationPlanCreate(BaseModel):
    warning_id: int
    district: str
    plan_data: Any
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    approver: Optional[str] = None


class ResourceAllocationPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    warning_id: int
    district: str
    plan_data: Any
    cross_district_summary: Any = dict
    approval_status: ApprovalStatus
    approver: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime


class ResourceAllocationCreate(BaseModel):
    plan_id: int
    warehouse_id: int
    material_type: MaterialType
    quantity: int
    distance_km: float = 0
    is_cross_district: bool = False
    estimated_arrival_hours: float = 0


class ResourceAllocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    warehouse_id: int
    material_type: MaterialType
    quantity: int
    distance_km: float
    is_cross_district: bool
    status: AllocationStatus
    shipped_at: Optional[datetime] = None
    arrived_at: Optional[datetime] = None
    receiver: Optional[str] = None
    consumed_quantity: int
    estimated_arrival_hours: float


class ShipmentConfirmRequest(BaseModel):
    allocation_id: int


class ArrivalConfirmRequest(BaseModel):
    allocation_id: int
    receiver: str


class ConsumptionReportRequest(BaseModel):
    allocation_id: int
    consumed_quantity: int


class InspectionOrderCreate(BaseModel):
    warning_id: Optional[int] = None
    inspector_name: str
    district: str
    location: str
    longitude: float
    latitude: float
    status: WorkOrderStatus = WorkOrderStatus.PENDING


class InspectionOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    warning_id: Optional[int] = None
    inspector_name: str
    district: str
    location: str
    longitude: float
    latitude: float
    status: WorkOrderStatus
    created_at: datetime
    completed_at: Optional[datetime] = None


class InspectionReportCreate(BaseModel):
    order_id: int
    water_depth: float
    photo_url: Optional[str] = None
    description: str = ""
    needs_traffic_control: bool = False
    adjacent_confirmed: bool = False


class InspectionReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    water_depth: float
    photo_url: Optional[str] = None
    description: str
    needs_traffic_control: bool
    adjacent_confirmed: bool
    reported_at: datetime


class TrafficControlPlanCreate(BaseModel):
    inspection_report_id: int
    district: str
    location: str
    control_type: TrafficControlType
    description: str = ""
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    approver: Optional[str] = None
    screen_updated: bool = False


class TrafficControlPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    inspection_report_id: int
    district: str
    location: str
    control_type: TrafficControlType
    description: str
    approval_status: ApprovalStatus
    approver: Optional[str] = None
    approved_at: Optional[datetime] = None
    screen_updated: bool
    created_at: datetime


class GuideScreenUpdate(BaseModel):
    code: Optional[str] = None
    location: Optional[str] = None
    district: Optional[str] = None
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    current_content: Optional[str] = None


class GuideScreenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    location: str
    district: str
    longitude: float
    latitude: float
    current_content: str
    updated_at: datetime


class HiddenDangerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    location: str
    district: str
    longitude: float
    latitude: float
    waterlogging_count: int
    last_waterlogging_at: Optional[datetime] = None
    is_high_risk: bool
    renovation_suggestion: str
    pushed_to_planning: bool
    in_annual_plan: bool
    created_at: datetime
    updated_at: datetime


class WaterloggingEventCreate(BaseModel):
    location: str
    district: str
    longitude: float
    latitude: float
    water_depth: float
    warning_id: Optional[int] = None


class WaterloggingEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    location: str
    district: str
    longitude: float
    latitude: float
    water_depth: float
    warning_id: Optional[int] = None
    recorded_at: datetime


class MaintenanceOrderCreate(BaseModel):
    device_id: int
    description: str = ""
    required_skills: str = ""
    assigned_team: Optional[str] = None
    status: WorkOrderStatus = WorkOrderStatus.PENDING


class MaintenanceOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    description: str
    required_skills: str
    assigned_team: Optional[str] = None
    status: WorkOrderStatus
    completed_at: Optional[datetime] = None
    created_at: datetime


class MaintenanceTeamCreate(BaseModel):
    name: str
    skills: str = ""
    district: str
    longitude: float = 0
    latitude: float = 0
    available: bool = True


class MaintenanceTeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    skills: str
    district: str
    longitude: float
    latitude: float
    available: bool


class ReplenishmentRequestCreate(BaseModel):
    warehouse_id: int
    material_type: MaterialType
    current_quantity: int
    safety_stock: int
    request_quantity: int
    district_approval_status: ApprovalStatus = ApprovalStatus.PENDING
    district_approver: Optional[str] = None
    city_approval_status: ApprovalStatus = ApprovalStatus.PENDING
    city_approver: Optional[str] = None
    procurement_synced: bool = False


class ReplenishmentRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    warehouse_id: int
    material_type: MaterialType
    current_quantity: int
    safety_stock: int
    request_quantity: int
    district_approval_status: ApprovalStatus
    district_approver: Optional[str] = None
    district_approved_at: Optional[datetime] = None
    city_approval_status: ApprovalStatus
    city_approver: Optional[str] = None
    city_approved_at: Optional[datetime] = None
    procurement_synced: bool
    created_at: datetime
    district_reminder_count: int
    city_reminder_count: int


class ApprovalReminderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int
    level: str
    reminder_count: int
    escalated: bool
    content: str
    created_at: datetime


class DailyReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_date: date
    district: str
    total_discharge: float
    total_energy: float
    avg_response_time: float
    material_consumption: Any
    material_shipped: Any
    material_arrived: Any
    pump_stats: Any
    generated_at: datetime


class PushMessageCreate(BaseModel):
    target_role: str
    category: str
    title: str
    content: str = ""
    related_id: Optional[int] = None
    related_type: Optional[str] = None
    read: bool = False


class PushMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_role: str
    category: str
    title: str
    content: str
    related_id: Optional[int] = None
    related_type: Optional[str] = None
    read: bool
    created_at: datetime


class RiskCalculationRequest(BaseModel):
    district: str
    rainfall_intensity: float
    pipe_usage_ratio: float
    elevation_risk: float = 0


class RiskCalculationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    district: str
    risk_level: RiskLevel
    rainfall_intensity: float
    pipe_usage_ratio: float
    elevation_risk: float
