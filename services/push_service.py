from models import PushMessage
from database import SessionLocal


VALID_TARGET_ROLES = {"headquarters", "inspector", "pump_duty", "traffic_dept", "planning_dept", "maintenance_team"}
VALID_CATEGORIES = {"warning", "work_order", "approval", "dispatch"}


def push_message(db, target_role, category, title, content, related_id=None, related_type=None):
    if target_role not in VALID_TARGET_ROLES:
        raise ValueError(f"Invalid target_role: {target_role}")
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category: {category}")
    msg = PushMessage(
        target_role=target_role,
        category=category,
        title=title,
        content=content,
        related_id=related_id,
        related_type=related_type,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def push_warning(db, target_role, title, content, related_id=None, related_type=None):
    return push_message(db, target_role, "warning", title, content, related_id, related_type)


def push_work_order(db, target_role, title, content, related_id=None, related_type=None):
    return push_message(db, target_role, "work_order", title, content, related_id, related_type)


def push_approval(db, target_role, title, content, related_id=None, related_type=None):
    return push_message(db, target_role, "approval", title, content, related_id, related_type)


def push_dispatch(db, target_role, title, content, related_id=None, related_type=None):
    return push_message(db, target_role, "dispatch", title, content, related_id, related_type)
