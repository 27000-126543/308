from datetime import datetime
from sqlalchemy.orm import Session
from models import UrgeRecord, UrgeTargetType
from services.push_service import push_message


def create_urge(db: Session, target_type: UrgeTargetType, target_id: int,
                urger: str, warning_id: int = None, remark: str = "") -> UrgeRecord:
    existing = db.query(UrgeRecord).filter(
        UrgeRecord.target_type == target_type,
        UrgeRecord.target_id == target_id
    ).first()

    if existing:
        existing.urge_count += 1
        existing.last_urged_at = datetime.utcnow()
        existing.urger = urger
        if remark:
            existing.remark = remark
        db.commit()
        db.refresh(existing)

        push_message(
            db=db,
            target_role="headquarters",
            category="dispatch",
            title=f"重复催办-{target_type.value}",
            content=f"{urger}对{target_type.value}(ID:{target_id})发起第{existing.urge_count}次催办",
            related_id=target_id,
            related_type=target_type.value
        )
        return existing

    record = UrgeRecord(
        target_type=target_type,
        target_id=target_id,
        warning_id=warning_id,
        urger=urger,
        urge_count=1,
        last_urged_at=datetime.utcnow(),
        remark=remark
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    push_message(
        db=db,
        target_role="headquarters",
        category="dispatch",
        title=f"催办-{target_type.value}",
        content=f"{urger}对{target_type.value}(ID:{target_id})发起催办",
        related_id=target_id,
        related_type=target_type.value
    )
    return record


def get_urges_by_warning(db: Session, warning_id: int):
    return db.query(UrgeRecord).filter(
        UrgeRecord.warning_id == warning_id
    ).order_by(UrgeRecord.last_urged_at.desc()).all()


def get_urges_by_target(db: Session, target_type: UrgeTargetType = None,
                        target_id: int = None):
    query = db.query(UrgeRecord)
    if target_type:
        query = query.filter(UrgeRecord.target_type == target_type)
    if target_id:
        query = query.filter(UrgeRecord.target_id == target_id)
    return query.order_by(UrgeRecord.last_urged_at.desc()).all()
