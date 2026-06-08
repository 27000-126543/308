from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import (
    Warehouse, MaterialInventory, ResourceAllocationPlan,
    ResourceAllocation, MaterialType, ApprovalStatus, AllocationStatus
)
from schemas import (
    WarehouseCreate, WarehouseResponse,
    MaterialInventoryCreate, MaterialInventoryResponse,
    ResourceAllocationPlanResponse, ResourceAllocationResponse,
    ShipmentConfirmRequest, ArrivalConfirmRequest, ConsumptionReportRequest
)
from services.dispatch_service import (
    approve_resource_plan, reject_resource_plan,
    confirm_shipment, confirm_arrival, report_consumption
)
from services.replenishment_service import (
    check_inventory_levels, approve_district_level, approve_city_level
)

router = APIRouter(prefix="/api/materials", tags=["物资管理"])


@router.post("/warehouses", response_model=WarehouseResponse)
def create_warehouse(data: WarehouseCreate, db: Session = Depends(get_db)):
    wh = Warehouse(**data.model_dump())
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return wh


@router.get("/warehouses", response_model=list[WarehouseResponse])
def list_warehouses(district: str = None, db: Session = Depends(get_db)):
    query = db.query(Warehouse)
    if district:
        query = query.filter(Warehouse.district == district)
    return query.all()


@router.post("/inventories", response_model=MaterialInventoryResponse)
def create_inventory(data: MaterialInventoryCreate, db: Session = Depends(get_db)):
    inv = MaterialInventory(**data.model_dump())
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


@router.get("/inventories", response_model=list[MaterialInventoryResponse])
def list_inventories(warehouse_id: int = None, material_type: MaterialType = None,
                     db: Session = Depends(get_db)):
    query = db.query(MaterialInventory)
    if warehouse_id:
        query = query.filter(MaterialInventory.warehouse_id == warehouse_id)
    if material_type:
        query = query.filter(MaterialInventory.material_type == material_type)
    return query.all()


@router.get("/inventories/below-safety", response_model=list[MaterialInventoryResponse])
def get_inventories_below_safety(db: Session = Depends(get_db)):
    results = []
    inventories = db.query(MaterialInventory).all()
    for inv in inventories:
        available = inv.quantity - inv.locked_quantity
        if available < inv.safety_stock:
            results.append(inv)
    return results


@router.post("/check-inventory")
def check_inventory(db: Session = Depends(get_db)):
    check_inventory_levels(db)
    return {"message": "库存检查完成"}


@router.get("/allocation-plans", response_model=list[ResourceAllocationPlanResponse])
def list_allocation_plans(warning_id: int = None, approval_status: ApprovalStatus = None,
                           db: Session = Depends(get_db)):
    query = db.query(ResourceAllocationPlan)
    if warning_id:
        query = query.filter(ResourceAllocationPlan.warning_id == warning_id)
    if approval_status:
        query = query.filter(ResourceAllocationPlan.approval_status == approval_status)
    return query.order_by(ResourceAllocationPlan.created_at.desc()).all()


@router.get("/allocation-plans/{plan_id}", response_model=ResourceAllocationPlanResponse)
def get_allocation_plan(plan_id: int, db: Session = Depends(get_db)):
    return db.query(ResourceAllocationPlan).filter(ResourceAllocationPlan.id == plan_id).first()


@router.put("/allocation-plans/{plan_id}/approve", response_model=ResourceAllocationPlanResponse)
def approve_plan(plan_id: int, approver: str, db: Session = Depends(get_db)):
    return approve_resource_plan(db, plan_id, approver)


@router.put("/allocation-plans/{plan_id}/reject", response_model=ResourceAllocationPlanResponse)
def reject_plan(plan_id: int, approver: str, db: Session = Depends(get_db)):
    return reject_resource_plan(db, plan_id, approver)


@router.get("/allocations", response_model=list[ResourceAllocationResponse])
def list_allocations(plan_id: int = None, status: AllocationStatus = None,
                     is_cross_district: bool = None, db: Session = Depends(get_db)):
    query = db.query(ResourceAllocation)
    if plan_id:
        query = query.filter(ResourceAllocation.plan_id == plan_id)
    if status:
        query = query.filter(ResourceAllocation.status == status)
    if is_cross_district is not None:
        query = query.filter(ResourceAllocation.is_cross_district == is_cross_district)
    return query.all()


@router.put("/allocations/{allocation_id}/ship", response_model=ResourceAllocationResponse)
def ship_allocation(allocation_id: int, db: Session = Depends(get_db)):
    return confirm_shipment(db, allocation_id)


@router.put("/allocations/{allocation_id}/arrive", response_model=ResourceAllocationResponse)
def arrive_allocation(allocation_id: int, receiver: str, db: Session = Depends(get_db)):
    return confirm_arrival(db, allocation_id, receiver)


@router.put("/allocations/{allocation_id}/consume", response_model=ResourceAllocationResponse)
def consume_allocation(allocation_id: int, consumed_quantity: int, db: Session = Depends(get_db)):
    return report_consumption(db, allocation_id, consumed_quantity)


@router.put("/replenishment/{request_id}/approve-district", response_model=dict)
def approve_replenishment_district(request_id: int, approver: str, db: Session = Depends(get_db)):
    req = approve_district_level(db, request_id, approver)
    return {"message": "区级审批通过", "request_id": req.id}


@router.put("/replenishment/{request_id}/approve-city", response_model=dict)
def approve_replenishment_city(request_id: int, approver: str, db: Session = Depends(get_db)):
    req = approve_city_level(db, request_id, approver)
    return {"message": "市级审批通过，已同步采购", "request_id": req.id}
