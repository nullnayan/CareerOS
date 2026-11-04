"""Back up and apply explicitly requested source setup / catalogue clearing.

No network discovery and no service management. Default is a read-only summary.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db.session import SessionLocal
from db.models import (WorkspaceSettings, User, JobPosting, JobMatch, JobSource, JobSourceOccurrence,
    JobDescriptionRevision, JobSearchPreferences, JobRefreshRun, AutomationSettings, AutomationTask, JobApplication)
from jobs.connections import connect_free_defaults
from jobs.search_control import clear_listings


def rows(query):
    return [{column.name: getattr(row, column.name) for column in row.__table__.columns} for row in query]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--connect-free", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        workspace = db.get(WorkspaceSettings, 1)
        if not workspace: raise SystemExit("No existing workspace selected; no changes made.")
        owner = db.get(User, workspace.owner_id)
        if not owner: raise SystemExit("Workspace owner is missing; no changes made.")
        jobs = db.query(JobPosting).filter_by(user_id=owner.id)
        identifiers = [row.id for row in jobs]
        summary = {"jobs_before": len(identifiers), "apply": args.apply}
        if not args.apply: print(json.dumps(summary)); return
        if db.query(AutomationTask).filter_by(user_id=owner.id, status="running").first():
            raise SystemExit("A task is running. No changes made; let it finish before applying setup.")
        snapshot = {model.__tablename__: rows(db.query(model).filter_by(user_id=owner.id)) for model in
            (JobPosting, JobMatch, JobSource, JobSearchPreferences, JobRefreshRun, AutomationSettings, AutomationTask, JobApplication)}
        snapshot[JobSourceOccurrence.__tablename__] = rows(db.query(JobSourceOccurrence).filter(JobSourceOccurrence.job_id.in_(identifiers)))
        snapshot[JobDescriptionRevision.__tablename__] = rows(db.query(JobDescriptionRevision).filter(JobDescriptionRevision.job_id.in_(identifiers)))
        backup_dir = Path(__file__).resolve().parents[2] / ".implementation-backups" / "connection-architecture"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / (datetime.utcnow().strftime("%Y%m%dT%H%M%S%f") + ".json")
        with backup.open("x", encoding="utf-8") as stream:
            json.dump(snapshot, stream, default=str, ensure_ascii=False)
        summary["backup"] = str(backup)
        if args.clear:
            summary["clearing"] = clear_listings(db, owner)
            prefs = db.get(JobSearchPreferences, owner.id)
            if prefs: prefs.data = {**prefs.data, "minimum_salary_annual_inr": max(550000, prefs.data.get("minimum_salary_annual_inr") or 0)}
            db.commit()
        if args.connect_free: summary["connections"] = connect_free_defaults(db, owner)
        summary["jobs_visible_after"] = db.query(JobPosting).filter(JobPosting.user_id == owner.id, JobPosting.status != "cleared").count()
        print(json.dumps(summary))


if __name__ == "__main__": main()
