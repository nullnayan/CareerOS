"""Run: python -m automation.worker (keep this terminal open)."""
import logging
import threading
import uuid
from datetime import datetime
from sqlalchemy import text
from db.session import SessionLocal, engine
from db.models import AutomationWorker
from automation.service import process_one

log = logging.getLogger("careeros.worker")


def main():
    logging.basicConfig(level=logging.INFO)
    identifier = str(uuid.uuid4())
    stopped = threading.Event()
    # A session-level leadership lock serializes compilers across worker processes.
    with engine.connect() as leader:
        if engine.dialect.name == "postgresql":
            if not leader.execute(text("SELECT pg_try_advisory_lock(30103102)")).scalar():
                log.error("Another CareerOS worker is running. Keep only one worker terminal open.")
                return
        def heartbeat():
            while not stopped.is_set():
                try:
                    with SessionLocal() as db:
                        row = db.get(AutomationWorker, identifier)
                        if not row: row = AutomationWorker(id=identifier); db.add(row)
                        row.heartbeat_at = datetime.utcnow()
                        db.commit()
                except Exception:
                    log.warning("Database unavailable; heartbeat will retry.")
                stopped.wait(10)
        pulse = threading.Thread(target=heartbeat, daemon=True)
        pulse.start()
        log.info("CareerOS worker ready. Schedules run while this terminal and Docker remain open.")
        try:
            while not stopped.is_set():
                # Only the main thread touches the leadership connection. Losing
                # it releases the session advisory lock, so never reconnect and
                # continue processing beside a new leader.
                try:
                    leader.execute(text("SELECT 1"))
                except Exception:
                    log.error("Worker leadership connection was lost. Restart this worker terminal to recover safely.")
                    stopped.set()
                    break
                try:
                    if process_one(SessionLocal, identifier):
                        log.info("Background task completed; status saved in Automation.")
                    else: stopped.wait(3)
                except Exception:
                    log.warning("Worker cycle failed; database or source may be unavailable. Retrying in 15 seconds.")
                    stopped.wait(15)
        except KeyboardInterrupt:
            log.info("Stopping worker. Durable pending tasks remain available for the next start.")
        finally:
            stopped.set()
            pulse.join(timeout=2)
            try:
                with SessionLocal() as db:
                    row = db.get(AutomationWorker, identifier)
                    if row: db.delete(row); db.commit()
            finally:
                if engine.dialect.name == "postgresql":
                    try:
                        leader.execute(text("SELECT pg_advisory_unlock(30103102)"))
                    except Exception:
                        log.warning("Leadership connection was already closed.")


if __name__ == "__main__": main()
