from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import PushMessage
from schemas import PushMessageCreate, PushMessageResponse

router = APIRouter(prefix="/api/messages", tags=["消息推送"])


@router.post("", response_model=PushMessageResponse)
def send_message(data: PushMessageCreate, db: Session = Depends(get_db)):
    from services.push_service import push_message
    return push_message(
        db=db,
        target_role=data.target_role,
        category=data.category,
        title=data.title,
        content=data.content,
        related_id=data.related_id,
        related_type=data.related_type
    )


@router.get("", response_model=list[PushMessageResponse])
def list_messages(target_role: str = None, category: str = None,
                  unread_only: bool = False, limit: int = 50,
                  db: Session = Depends(get_db)):
    query = db.query(PushMessage)
    if target_role:
        query = query.filter(PushMessage.target_role == target_role)
    if category:
        query = query.filter(PushMessage.category == category)
    if unread_only:
        query = query.filter(PushMessage.read == False)
    return query.order_by(PushMessage.created_at.desc()).limit(limit).all()


@router.put("/{message_id}/read", response_model=PushMessageResponse)
def mark_as_read(message_id: int, db: Session = Depends(get_db)):
    msg = db.query(PushMessage).filter(PushMessage.id == message_id).first()
    if not msg:
        return None
    msg.read = True
    db.commit()
    db.refresh(msg)
    return msg


@router.put("/read-all")
def mark_all_as_read(target_role: str, db: Session = Depends(get_db)):
    db.query(PushMessage).filter(
        PushMessage.target_role == target_role,
        PushMessage.read == False
    ).update({"read": True})
    db.commit()
    return {"message": "全部标为已读"}


@router.get("/unread-count")
def get_unread_count(target_role: str, db: Session = Depends(get_db)):
    count = db.query(PushMessage).filter(
        PushMessage.target_role == target_role,
        PushMessage.read == False
    ).count()
    return {"target_role": target_role, "unread_count": count}
