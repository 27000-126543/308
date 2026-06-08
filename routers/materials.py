from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import (
    Warehouse, MaterialInventory, ResourceAllocationPlan,
    ResourceAllocation, MaterialType, ApprovalStatus
)
from schemas import (
    WarehouseCreate, WarehouseResponse,
    MaterialInventoryCreate, MaterialInventoryResponse,
    ResourceAllocationPlanResponse, ResourceAllocationResponse
)
from services.dispatch_service import approve_resource_plan, reject_resource_plan
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
    from sqlalchemy import or_
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


@router.put("/allocation-plans/{plan_id}/approve", response_model=ResourceAllocationPlanResponse)
def approve_plan(plan_id: int, approver: str, db: Session = Depends(get_db)):
    return approve_resource_plan(db, plan_id, approver)


@router.put("/allocation-plans/{plan_id}/reject", response_model=ResourceAllocationPlanResponse)
def reject_plan(plan_id: int, approver: str, db: Session = Depends(get_db)):
    return reject_resource_plan(db, plan_id, approver)


@router.get("/allocations", response_model=list[ResourceAllocationResponse])
def list_allocations(plan_id: int = None, db: Session = Depends(get_db)):
    query = db.query(ResourceAllocation)
    if plan_id:
        query = query.filter(ResourceAllocation.plan_id == plan_id)
    return query.all()


@router.put("/replenishment/{request_id}/approve-district", response_model=dict)
def approve_replenishment_district(request_id: int, approver: str, db: Session = Depends(get_db)):
    req = approve_district_level(db, request_id, approver)
    return {"message": "区级审批通过", "request_id": req.id}


@router.put("/replenishment/{request_id}/approve-city", response_model=dict)
def approve_replenishment_city(request_id: int, approver: str, db: Session = Depends(get_db)):
    req = approve_city_level(db, request_id, approver)
    return {"message": "市级审批通过，已同步采购", "request_id": req.id}
