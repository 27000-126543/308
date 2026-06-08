import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Enum, Text, Boolean,
    ForeignKey, JSON, Date
)
from sqlalchemy.orm import relationship
from database import Base


class RiskLevel(str, enum.Enum):
    BLUE = "blue"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT_ESCALATED = "timeout_escalated"


class WorkOrderStatus(str, enum.Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CLOSED = "closed"


class WarningStatus(str, enum.Enum):
    ACTIVE = "active"
    LIFTED = "lifted"


class MaterialType(str, enum.Enum):
    WATER_PUMP = "water_pump"
    SANDBAG = "sandbag"
    ASSAULT_BOAT = "assault_boat"


class StationType(str, enum.Enum):
    RAIN = "rain"
    WATER_LEVEL = "water_level"


class DeviceStatus(str, enum.Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    MAINTENANCE = "maintenance"
    FAULT = "fault"


class TrafficControlType(str, enum.Enum):
    ROAD_CLOSURE = "road_closure"
    TRAFFIC_DIVERSION = "traffic_diversion"


class AllocationStatus(str, enum.Enum):
    LOCKED = "locked"
    SHIPPED = "shipped"
    ARRIVED = "arrived"
    CONSUMED = "consumed"


class RainStation(Base):
    __tablename__ = "rain_stations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    district = Column(String(50), nullable=False)
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    elevation = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    records = relationship("RainRecord", back_populates="station")


class WaterLevelStation(Base):
    __tablename__ = "water_level_stations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    district = Column(String(50), nullable=False)
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    warning_level = Column(Float, nullable=False)
    guarantee_level = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    records = relationship("WaterLevelRecord", back_populates="station")


class RainRecord(Base):
    __tablename__ = "rain_records"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("rain_stations.id"), nullable=False)
    rainfall_1h = Column(Float, nullable=False)
    rainfall_3h = Column(Float, default=0)
    rainfall_6h = Column(Float, default=0)
    rainfall_24h = Column(Float, default=0)
    recorded_at = Column(DateTime, default=datetime.utcnow)
    station = relationship("RainStation", back_populates="records")


class WaterLevelRecord(Base):
    __tablename__ = "water_level_records"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("water_level_stations.id"), nullable=False)
    water_level = Column(Float, nullable=False)
    flow_rate = Column(Float, default=0)
    recorded_at = Column(DateTime, default=datetime.utcnow)
    station = relationship("WaterLevelStation", back_populates="records")


class PipeNetwork(Base):
    __tablename__ = "pipe_networks"
    id = Column(Integer, primary_key=True, index=True)
    district = Column(String(50), nullable=False)
    total_capacity = Column(Float, nullable=False)
    current_usage = Column(Float, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)


class GroundElevation(Base):
    __tablename__ = "ground_elevations"
    id = Column(Integer, primary_key=True, index=True)
    district = Column(String(50), nullable=False)
    area_name = Column(String(100), nullable=False)
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    elevation = Column(Float, nullable=False)
    drainage_grade = Column(String(20), default="P3")


class Warning(Base):
    __tablename__ = "warnings"
    id = Column(Integer, primary_key=True, index=True)
    district = Column(String(50), nullable=False)
    risk_level = Column(Enum(RiskLevel), nullable=False)
    rainfall_intensity = Column(Float, nullable=False)
    pipe_usage_ratio = Column(Float, nullable=False)
    elevation_risk = Column(Float, default=0)
    status = Column(Enum(WarningStatus), default=WarningStatus.ACTIVE)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    lifted_at = Column(DateTime, nullable=True)
    dispatches = relationship("PumpDispatch", back_populates="warning")
    resource_plans = relationship("ResourceAllocationPlan", back_populates="warning")


class PumpStation(Base):
    __tablename__ = "pump_stations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    district = Column(String(50), nullable=False)
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    design_capacity = Column(Float, nullable=False)
    current_discharge = Column(Float, default=0)
    status = Column(Enum(DeviceStatus), default=DeviceStatus.STOPPED)
    created_at = Column(DateTime, default=datetime.utcnow)
    devices = relationship("PumpDevice", back_populates="station")
    dispatches = relationship("PumpDispatch", back_populates="station")
    operation_logs = relationship("PumpOperationLog", back_populates="station")


class PumpDevice(Base):
    __tablename__ = "pump_devices"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("pump_stations.id"), nullable=False)
    name = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    rated_power = Column(Float, nullable=False)
    running_hours = Column(Float, default=0)
    maintenance_cycle_hours = Column(Float, default=2000)
    last_maintenance_at = Column(DateTime, nullable=True)
    status = Column(Enum(DeviceStatus), default=DeviceStatus.STOPPED)
    station = relationship("PumpStation", back_populates="devices")
    maintenance_orders = relationship("MaintenanceOrder", back_populates="device")


class PumpDispatch(Base):
    __tablename__ = "pump_dispatches"
    id = Column(Integer, primary_key=True, index=True)
    warning_id = Column(Integer, ForeignKey("warnings.id"), nullable=False)
    station_id = Column(Integer, ForeignKey("pump_stations.id"), nullable=False)
    target_discharge = Column(Float, nullable=False)
    instruction = Column(Text, default="")
    status = Column(String(20), default="issued")
    issued_at = Column(DateTime, default=datetime.utcnow)
    acknowledged_at = Column(DateTime, nullable=True)
    warning = relationship("Warning", back_populates="dispatches")
    station = relationship("PumpStation", back_populates="dispatches")


class PumpOperationLog(Base):
    __tablename__ = "pump_operation_logs"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("pump_stations.id"), nullable=False)
    discharge_volume = Column(Float, default=0)
    energy_consumption = Column(Float, default=0)
    running_hours = Column(Float, default=0)
    recorded_at = Column(DateTime, default=datetime.utcnow)
    station = relationship("PumpStation", back_populates="operation_logs")


class Warehouse(Base):
    __tablename__ = "warehouses"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    district = Column(String(50), nullable=False)
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    inventories = relationship("MaterialInventory", back_populates="warehouse")


class MaterialInventory(Base):
    __tablename__ = "material_inventories"
    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    material_type = Column(Enum(MaterialType), nullable=False)
    quantity = Column(Integer, nullable=False)
    safety_stock = Column(Integer, nullable=False)
    locked_quantity = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)
    warehouse = relationship("Warehouse", back_populates="inventories")


class ResourceAllocationPlan(Base):
    __tablename__ = "resource_allocation_plans"
    id = Column(Integer, primary_key=True, index=True)
    warning_id = Column(Integer, ForeignKey("warnings.id"), nullable=False)
    district = Column(String(50), nullable=False)
    plan_data = Column(JSON, nullable=False)
    cross_district_summary = Column(JSON, default=dict)
    approval_status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING)
    approver = Column(String(100), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    warning = relationship("Warning", back_populates="resource_plans")
    allocations = relationship("ResourceAllocation", back_populates="plan")


class ResourceAllocation(Base):
    __tablename__ = "resource_allocations"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("resource_allocation_plans.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    material_type = Column(Enum(MaterialType), nullable=False)
    quantity = Column(Integer, nullable=False)
    distance_km = Column(Float, default=0)
    is_cross_district = Column(Boolean, default=False)
    status = Column(Enum(AllocationStatus), default=AllocationStatus.LOCKED)
    shipped_at = Column(DateTime, nullable=True)
    arrived_at = Column(DateTime, nullable=True)
    receiver = Column(String(100), nullable=True)
    consumed_quantity = Column(Integer, default=0)
    estimated_arrival_hours = Column(Float, default=0)
    plan = relationship("ResourceAllocationPlan", back_populates="allocations")


class InspectionOrder(Base):
    __tablename__ = "inspection_orders"
    id = Column(Integer, primary_key=True, index=True)
    warning_id = Column(Integer, ForeignKey("warnings.id"), nullable=True)
    inspector_name = Column(String(100), nullable=False)
    district = Column(String(50), nullable=False)
    location = Column(String(200), nullable=False)
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    status = Column(Enum(WorkOrderStatus), default=WorkOrderStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    reports = relationship("InspectionReport", back_populates="order")


class InspectionReport(Base):
    __tablename__ = "inspection_reports"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("inspection_orders.id"), nullable=False)
    water_depth = Column(Float, nullable=False)
    photo_url = Column(String(500), nullable=True)
    description = Column(Text, default="")
    needs_traffic_control = Column(Boolean, default=False)
    adjacent_confirmed = Column(Boolean, default=False)
    reported_at = Column(DateTime, default=datetime.utcnow)
    order = relationship("InspectionOrder", back_populates="reports")


class TrafficControlPlan(Base):
    __tablename__ = "traffic_control_plans"
    id = Column(Integer, primary_key=True, index=True)
    inspection_report_id = Column(Integer, ForeignKey("inspection_reports.id"), nullable=False)
    district = Column(String(50), nullable=False)
    location = Column(String(200), nullable=False)
    control_type = Column(Enum(TrafficControlType), nullable=False)
    description = Column(Text, default="")
    approval_status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING)
    approver = Column(String(100), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    screen_updated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class GuideScreen(Base):
    __tablename__ = "guide_screens"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False)
    location = Column(String(200), nullable=False)
    district = Column(String(50), nullable=False)
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    current_content = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow)


class HiddenDanger(Base):
    __tablename__ = "hidden_dangers"
    id = Column(Integer, primary_key=True, index=True)
    location = Column(String(200), nullable=False)
    district = Column(String(50), nullable=False)
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    waterlogging_count = Column(Integer, default=0)
    last_waterlogging_at = Column(DateTime, nullable=True)
    is_high_risk = Column(Boolean, default=False)
    renovation_suggestion = Column(Text, default="")
    pushed_to_planning = Column(Boolean, default=False)
    in_annual_plan = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class WaterloggingEvent(Base):
    __tablename__ = "waterlogging_events"
    id = Column(Integer, primary_key=True, index=True)
    location = Column(String(200), nullable=False)
    district = Column(String(50), nullable=False)
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    water_depth = Column(Float, nullable=False)
    warning_id = Column(Integer, ForeignKey("warnings.id"), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)


class MaintenanceOrder(Base):
    __tablename__ = "maintenance_orders"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("pump_devices.id"), nullable=False)
    description = Column(Text, default="")
    required_skills = Column(String(200), default="")
    assigned_team = Column(String(100), nullable=True)
    status = Column(Enum(WorkOrderStatus), default=WorkOrderStatus.PENDING)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    device = relationship("PumpDevice", back_populates="maintenance_orders")


class MaintenanceTeam(Base):
    __tablename__ = "maintenance_teams"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    skills = Column(String(500), default="")
    district = Column(String(50), nullable=False)
    longitude = Column(Float, default=0)
    latitude = Column(Float, default=0)
    available = Column(Boolean, default=True)


class ReplenishmentRequest(Base):
    __tablename__ = "replenishment_requests"
    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    material_type = Column(Enum(MaterialType), nullable=False)
    current_quantity = Column(Integer, nullable=False)
    safety_stock = Column(Integer, nullable=False)
    request_quantity = Column(Integer, nullable=False)
    district_approval_status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING)
    district_approver = Column(String(100), nullable=True)
    district_approved_at = Column(DateTime, nullable=True)
    city_approval_status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING)
    city_approver = Column(String(100), nullable=True)
    city_approved_at = Column(DateTime, nullable=True)
    procurement_synced = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    district_reminder_count = Column(Integer, default=0)
    city_reminder_count = Column(Integer, default=0)


class ApprovalReminder(Base):
    __tablename__ = "approval_reminders"
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("replenishment_requests.id"), nullable=False)
    level = Column(String(20), nullable=False)
    reminder_count = Column(Integer, default=0)
    escalated = Column(Boolean, default=False)
    content = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyReport(Base):
    __tablename__ = "daily_reports"
    id = Column(Integer, primary_key=True, index=True)
    report_date = Column(Date, nullable=False)
    district = Column(String(50), nullable=False)
    total_discharge = Column(Float, default=0)
    total_energy = Column(Float, default=0)
    avg_response_time = Column(Float, default=0)
    material_consumption = Column(JSON, default=dict)
    material_shipped = Column(JSON, default=dict)
    material_arrived = Column(JSON, default=dict)
    pump_stats = Column(JSON, default=dict)
    generated_at = Column(DateTime, default=datetime.utcnow)


class PushMessage(Base):
    __tablename__ = "push_messages"
    id = Column(Integer, primary_key=True, index=True)
    target_role = Column(String(50), nullable=False)
    category = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, default="")
    related_id = Column(Integer, nullable=True)
    related_type = Column(String(50), nullable=True)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
