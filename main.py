from contextlib import asynccontextmanager
from datetime import date
from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from database import engine, SessionLocal, Base
from models import (
    RainStation, WaterLevelStation, RainRecord, WaterLevelRecord,
    PipeNetwork, GroundElevation, Warning, PumpStation, PumpDevice,
    PumpDispatch, PumpOperationLog, Warehouse, MaterialInventory,
    ResourceAllocationPlan, ResourceAllocation, InspectionOrder,
    InspectionReport, TrafficControlPlan, GuideScreen, HiddenDanger,
    WaterloggingEvent, MaintenanceOrder, MaintenanceTeam,
    ReplenishmentRequest, ApprovalReminder, DailyReport, PushMessage,
    ProcurementRecord, UrgeRecord
)
from routers import (
    stations_router, warnings_router, pump_router, materials_router,
    inspection_router, maintenance_router, system_router, messages_router
)
from services.maintenance_service import check_maintenance_cycles
from services.replenishment_service import check_inventory_levels, check_approval_timeouts
from services.report_service import generate_daily_report


Base.metadata.create_all(bind=engine)

scheduler = BackgroundScheduler()


def scheduled_maintenance_check():
    db = SessionLocal()
    try:
        check_maintenance_cycles(db)
    finally:
        db.close()


def scheduled_inventory_check():
    db = SessionLocal()
    try:
        check_inventory_levels(db)
    finally:
        db.close()


def scheduled_approval_timeout_check():
    db = SessionLocal()
    try:
        check_approval_timeouts(db)
    finally:
        db.close()


def scheduled_daily_report():
    db = SessionLocal()
    try:
        yesterday = date.today()
        from datetime import timedelta
        yesterday = yesterday - timedelta(days=1)
        generate_daily_report(db, yesterday)
    finally:
        db.close()


scheduler.add_job(scheduled_maintenance_check, "interval", hours=1, id="maintenance_check")
scheduler.add_job(scheduled_inventory_check, "interval", hours=2, id="inventory_check")
scheduler.add_job(scheduled_approval_timeout_check, "interval", minutes=30, id="approval_timeout")
scheduler.add_job(scheduled_daily_report, "cron", hour=1, minute=0, id="daily_report")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title="城市防汛排涝与泵站联合调度系统",
    description="""
    ## 系统功能
    1. **实时监测**：雨量站/水位站数据上传，自动计算内涝风险等级(蓝黄橙红)，生成预警并触发泵站预排指令
    2. **应急资源调配**：橙色及以上预警自动生成调配方案(水泵/沙袋/冲锋舟)，指挥长审批后按距离智能分配，锁定库存
    3. **巡查与交通管制**：巡查上报积水数据，系统比对相邻点位，需要时生成交通管制方案推送交警审批，审批后更新诱导屏
    4. **高风险隐患**：30天重复积水超2次自动标记，生成改造建议推送市政规划部门
    5. **设备维保**：运行超保养周期自动生成维保工单，按技能和位置分配维修班组
    6. **物资补货**：库存低于安全线自动申请补货，市区两级审批(超时3小时催办升级)
    7. **日报生成**：每日凌晨自动生成排涝运行报告，支持按日期/片区导出
    8. **实时推送**：预警、工单、审批、调度指令实时推送至各部门
    """,
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(stations_router)
app.include_router(warnings_router)
app.include_router(pump_router)
app.include_router(materials_router)
app.include_router(inspection_router)
app.include_router(maintenance_router)
app.include_router(system_router)
app.include_router(messages_router)


@app.get("/")
def root():
    return {
        "system": "城市防汛排涝与泵站联合调度系统",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/api/dashboard/summary")
def dashboard_summary():
    db = SessionLocal()
    try:
        from models import Warning, WarningStatus, InspectionOrder, WorkOrderStatus
        from sqlalchemy import func

        active_warnings = db.query(Warning).filter(
            Warning.status == WarningStatus.ACTIVE
        ).count()

        pending_orders = db.query(InspectionOrder).filter(
            InspectionOrder.status.in_([WorkOrderStatus.PENDING, WorkOrderStatus.ASSIGNED])
        ).count()

        red_warnings = db.query(Warning).filter(
            Warning.status == WarningStatus.ACTIVE,
            Warning.risk_level == "red"
        ).count()

        orange_warnings = db.query(Warning).filter(
            Warning.status == WarningStatus.ACTIVE,
            Warning.risk_level == "orange"
        ).count()

        high_risk_dangers = db.query(HiddenDanger).filter(
            HiddenDanger.is_high_risk == True
        ).count()

        unread_messages = db.query(PushMessage).filter(
            PushMessage.read == False
        ).count()

        return {
            "active_warnings": active_warnings,
            "red_warnings": red_warnings,
            "orange_warnings": orange_warnings,
            "pending_orders": pending_orders,
            "high_risk_dangers": high_risk_dangers,
            "unread_messages": unread_messages,
        }
    finally:
        db.close()
