from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.workspace import get_workspace_owner
from db.session import get_db
from db.models import AutomationSettings, AutomationTask, AutomationWorker
from automation.service import (SettingsInput, settings_for, require_setup, lock_owner,
                                queue_discovery, queue_preparation, task_json, daily_prepared)

router = APIRouter(prefix="/automation", tags=["Automation"])


@router.get("")
def overview(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    row, config = settings_for(db, owner.id)
    heartbeat = db.query(AutomationWorker).order_by(AutomationWorker.heartbeat_at.desc()).first()
    return {"settings": config.model_dump(), "next_run_at": row.next_run_at.isoformat() if row and row.next_run_at else None,
            "last_run_at": row.last_run_at.isoformat() if row and row.last_run_at else None,
            "daily_prepared": daily_prepared(db, owner.id),
            "worker": {"running": bool(heartbeat and heartbeat.heartbeat_at > datetime.utcnow() - timedelta(seconds=35)),
                       "heartbeat_at": heartbeat.heartbeat_at.isoformat() if heartbeat else None},
            "tasks": [task_json(t) for t in db.query(AutomationTask).filter_by(user_id=owner.id).order_by(AutomationTask.created_at.desc()).limit(100)]}


@router.put("/settings")
def update(request: SettingsInput, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    lock_owner(db)
    if request.enabled: require_setup(db, owner.id)
    row, old = settings_for(db, owner.id)
    if not row:
        row = AutomationSettings(user_id=owner.id); db.add(row)
    row.data = request.model_dump()
    if request.enabled:
        if not old.enabled or old.interval_minutes != request.interval_minutes or not row.next_run_at:
            row.next_run_at = datetime.utcnow()
    else:
        row.next_run_at = None
        for task in db.query(AutomationTask).filter_by(user_id=owner.id, status="queued"):
            if task.payload.get("automatic"):
                task.status, task.finished_at = "cancelled", datetime.utcnow()
    db.commit()
    return overview(db, owner)


@router.post("/run")
def run_now(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    task = queue_discovery(db, owner.id)
    db.commit()
    return task_json(task)


@router.post("/prepare/{identifier}")
def prepare_job(identifier: str, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    task = queue_preparation(db, owner.id, identifier)
    db.commit()
    return task_json(task)


@router.post("/tasks/{identifier}/{action}")
def control(identifier: str, action: str, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    task = db.query(AutomationTask).filter_by(id=identifier, user_id=owner.id).with_for_update().first()
    if not task: raise HTTPException(404, "Task not found.")
    if action == "retry" and task.status in {"failed", "cancelled"}:
        from jobs.oss.cancellation import reset, token
        reset(token(owner.id, "task", task.id))
        task.status, task.error, task.finished_at = "queued", None, None
        task.attempts, task.available_at = 0, datetime.utcnow()
        task.payload = {**task.payload, "automatic": False}
    elif action == "cancel" and (task.status == "queued" or (task.kind == "discover" and task.status == "running")):
        from jobs.oss.cancellation import cancel, token
        cancel(token(owner.id, "task", task.id))
        task.status, task.finished_at = "cancelled", datetime.utcnow()
    else:
        raise HTTPException(409, "Queued tasks or running discovery can be cancelled; only failed/cancelled tasks can be retried.")
    db.commit()
    return task_json(task)
