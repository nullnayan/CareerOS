"""Durable queue and preparation contracts. All writes use isolated SQLite."""
from datetime import datetime, timedelta
from unittest.mock import patch
from types import SimpleNamespace
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from automation.service import (SettingsInput, queue_discovery, queue_preparation, enqueue,
    schedule_due, daily_prepared, claim, execute, process_one, retry_after_seconds)
from api.automation import router
from core.workspace import get_workspace_owner
from db.session import get_db
from db.models import (Base, User, WorkspaceSettings, JobSearchPreferences, JobSource,
    JobPosting, LatexMaster, ConfirmedSkill, LatexTailoringRun, AutomationTask, AutomationSettings)
from jobs.schemas import SearchPreferences
from tailoring.latex import digest


@pytest.fixture
def queue():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        owner = User(email="queue@example.com"); other = User(email="other@example.com")
        db.add_all([owner, other]); db.flush()
        db.add(WorkspaceSettings(id=1, owner_id=owner.id))
        db.add(JobSearchPreferences(user_id=owner.id, data=SearchPreferences().model_dump(mode="json")))
        db.add(JobSource(user_id=owner.id, provider="greenhouse", board="example", company="Example", enabled=True))
        source = r"\begin{document}\section{Skills}\textbf{Languages}{: Python}\textbf{Tools/Cloud}{: Git}\section{Projects}Example\end{document}"
        master = LatexMaster(user_id=owner.id, filename="qa.tex", source=source, source_hash=digest(source), categories=["Languages", "Tools/Cloud"], status="active", baseline_pages=1)
        text = "Graduate Software Engineer. Required Python and Docker. Fresh graduates welcome; no prior experience required."
        job = JobPosting(user_id=owner.id, identity_key="job", title="Graduate Software Engineer", company="Example", location="India", apply_url="https://example.com/job", description=text, description_hash=digest(text), description_complete=True, facts={})
        db.add_all([master, job]); db.commit()
    app = FastAPI(); app.include_router(router)
    def database():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_workspace_owner] = lambda: owner
    yield factory, owner, other, job, master, TestClient(app)
    engine.dispose()


def task(db, owner, kind="discover", **kwargs):
    row = enqueue(db, owner.id, kind, kwargs.pop("payload", {}), kwargs.pop("key", str(datetime.utcnow().timestamp())))
    for key, value in kwargs.items(): setattr(row, key, value)
    db.commit()
    return row


@pytest.mark.parametrize("field,value", [("interval_minutes", 14), ("interval_minutes", 1441), ("max_preparations", 0), ("daily_pdf_limit", 21), ("minimum_score", 101)])
def test_schedule_bounds_are_validated(field, value):
    with pytest.raises(ValidationError): SettingsInput(**{field: value})


def test_discovery_dedupes_pending_and_requires_setup(queue):
    factory, owner, *_ = queue
    with factory() as db:
        first = queue_discovery(db, owner.id); db.commit()
        assert queue_discovery(db, owner.id).id == first.id
        db.query(JobSource).delete(); db.commit()
        with pytest.raises(HTTPException) as error: queue_discovery(db, owner.id)
        assert error.value.status_code == 409


def test_preparation_dedupes_input_versions_and_confirmed_profile(queue):
    factory, owner, other, job, master, _ = queue
    with factory() as db:
        first = queue_preparation(db, owner.id, job.id); db.commit()
        assert queue_preparation(db, owner.id, job.id).id == first.id
        with pytest.raises(HTTPException): queue_preparation(db, other.id, job.id)
        db.add(ConfirmedSkill(user_id=owner.id, canonical="docker", name="Docker", category="Tools/Cloud")); db.commit()
        second = queue_preparation(db, owner.id, job.id); db.commit()
        assert second.id != first.id
        current = db.get(JobPosting, job.id); current.description += " SQL"; current.description_hash = digest(current.description); db.commit()
        assert queue_preparation(db, owner.id, job.id).id not in {first.id, second.id}


def test_preparation_requires_open_full_jd_and_active_master(queue):
    factory, owner, _, job, master, _ = queue
    with factory() as db:
        current = db.get(JobPosting, job.id); current.description_complete = False; db.commit()
        with pytest.raises(HTTPException): queue_preparation(db, owner.id, job.id)
        current.description_complete = True; current.status = "closed"; db.commit()
        with pytest.raises(HTTPException): queue_preparation(db, owner.id, job.id)
        current.status = "open"; db.get(LatexMaster, master.id).status = "draft"; db.commit()
        with pytest.raises(HTTPException): queue_preparation(db, owner.id, job.id)


def test_schedule_only_current_owner_and_advances_once(queue):
    factory, owner, other, *_ = queue
    now = datetime(2026, 10, 31, 8)
    with factory() as db:
        db.add_all([AutomationSettings(user_id=owner.id, data=SettingsInput(enabled=True, interval_minutes=60).model_dump(), next_run_at=now),
                    AutomationSettings(user_id=other.id, data=SettingsInput(enabled=True).model_dump(), next_run_at=now)])
        db.commit(); schedule_due(db, now)
        assert db.query(AutomationTask).one().user_id == owner.id
        assert db.get(AutomationSettings, owner.id).next_run_at == now + timedelta(hours=1)
        schedule_due(db, now + timedelta(minutes=1))
        assert db.query(AutomationTask).count() == 1


def test_india_daily_boundary_counts_only_successful_pdfs(queue):
    factory, owner, *_ = queue
    now = datetime(2026, 10, 31, 18, 31)
    with factory() as db:
        task(db, owner, "prepare", status="succeeded", finished_at=datetime(2026, 10, 31, 18, 29), result={"pdf_url": "/old"}, key="old")
        task(db, owner, "prepare", status="succeeded", finished_at=datetime(2026, 10, 31, 18, 30), result={"pdf_url": "/new"}, key="new")
        task(db, owner, "prepare", status="failed", finished_at=now, result={"pdf_url": "/failed"}, key="failed")
        assert daily_prepared(db, owner.id, now) == 1


def test_daily_cap_defers_to_next_india_midnight_without_attempt(queue):
    factory, owner, *_ = queue
    now = datetime(2026, 10, 31, 10)
    with factory() as db:
        db.add(AutomationSettings(user_id=owner.id, data=SettingsInput(daily_pdf_limit=1).model_dump())); db.commit()
        task(db, owner, "prepare", status="succeeded", finished_at=now, result={"pdf_url": "/ready"}, key="done")
        pending = task(db, owner, "prepare", available_at=now - timedelta(seconds=1), key="pending")
        assert claim(db, "worker", now) is None
        db.refresh(pending)
        assert pending.available_at == datetime(2026, 10, 31, 18, 30)
        assert pending.attempts == 0 and pending.status == "queued"


def test_expired_leases_recover_but_attempts_are_bounded(queue):
    factory, owner, *_ = queue
    now = datetime.utcnow()
    with factory() as db:
        recovered = task(db, owner, status="running", attempts=2, lease_owner="dead", lease_until=now - timedelta(seconds=1), available_at=now - timedelta(seconds=2), key="recover")
        exhausted = task(db, owner, status="running", attempts=3, lease_owner="dead", lease_until=now - timedelta(seconds=1), key="exhausted")
        assert claim(db, "new-worker", now) == recovered.id
        db.refresh(recovered); db.refresh(exhausted)
        assert recovered.attempts == 3 and recovered.lease_owner == "new-worker"
        assert exhausted.status == "failed" and exhausted.finished_at == now


def test_paused_automatic_tasks_are_skipped_but_manual_work_can_run(queue):
    factory, owner, *_ = queue
    now = datetime.utcnow()
    with factory() as db:
        automatic = task(db, owner, payload={"automatic": True}, available_at=now - timedelta(seconds=1), key="auto")
        manual = task(db, owner, available_at=now - timedelta(seconds=1), key="manual")
        assert claim(db, "worker", now) == manual.id
        db.refresh(automatic); assert automatic.status == "queued" and automatic.attempts == 0


def test_pause_cancels_queued_automatic_not_manual(queue):
    factory, owner, _, _, _, client = queue
    with factory() as db:
        automatic = task(db, owner, payload={"automatic": True}, key="auto")
        manual = task(db, owner, key="manual")
    assert client.put("/automation/settings", json={"enabled": False}).status_code == 200
    with factory() as db:
        assert db.get(AutomationTask, automatic.id).status == "cancelled"
        assert db.get(AutomationTask, manual.id).status == "queued"


def test_pause_during_discovery_does_not_spawn_preparations(queue):
    factory, owner, *_ = queue
    with factory() as db:
        db.add(AutomationSettings(user_id=owner.id, data=SettingsInput(enabled=True, minimum_score=0).model_dump())); db.commit()
        automatic = task(db, owner, payload={"automatic": True})
        def refresh(session, user, automatic=False):
            row = session.get(AutomationSettings, user.id); row.data = SettingsInput(enabled=False, minimum_score=0).model_dump(); session.commit()
            return {"status": "succeeded", "listed": 1}
        with patch("api.jobs.refresh", side_effect=refresh): output = execute(db, automatic)
        assert output["preparation_task_ids"] == []
        assert db.query(AutomationTask).count() == 1


def test_partial_automatic_discovery_queues_one_paced_continuation(queue):
    factory, owner, *_ = queue
    with factory() as db:
        config = SettingsInput(enabled=True, prepare_resumes=False)
        db.add(AutomationSettings(user_id=owner.id, data=config.model_dump())); db.commit()
        automatic = task(db, owner, payload={"automatic": True}, status="running")
        result = {"status": "partial", "sources": [{"cursor": "next"}], "deferred": []}
        with patch("api.jobs.refresh", return_value=result): execute(db, automatic)
        followup = db.query(AutomationTask).filter(AutomationTask.id != automatic.id).one()
        assert followup.payload["automatic"] and followup.available_at > datetime.utcnow() + timedelta(seconds=55)
        assert automatic.lease_until > datetime.utcnow() + timedelta(minutes=19)
        assert db.get(AutomationSettings, owner.id).data == config.model_dump()


def test_queued_job_expiring_before_preparation_does_not_compile(queue):
    factory, owner, _, job, master, _ = queue
    with factory() as db:
        preparation = queue_preparation(db, owner.id, job.id); db.commit()
        stored = db.get(JobPosting, job.id)
        stored.facts = {"source_expiry_at": (datetime.utcnow() - timedelta(seconds=1)).isoformat()}; db.commit()
        with patch("api.tailor.analyze", side_effect=AssertionError("Expired source must not prepare")):
            with pytest.raises(HTTPException) as exc: execute(db, preparation)
        assert exc.value.status_code == 410


def test_completed_newest_jobs_do_not_starve_other_jobs_and_pending_work_is_bounded(queue):
    factory, owner, _, first, _, _ = queue
    with factory() as db:
        db.add(AutomationSettings(user_id=owner.id, data=SettingsInput(enabled=True, minimum_score=0, max_preparations=1).model_dump()))
        jobs = [db.get(JobPosting, first.id)]
        for number in (2, 3):
            job = JobPosting(user_id=owner.id, identity_key=str(number), title="Graduate Software Engineer", company="Example",
                location="India", apply_url=f"https://example.com/job/{number}", description=first.description,
                description_hash=first.description_hash, description_complete=True, facts={})
            db.add(job); jobs.append(job)
        db.commit()
        for index, job in enumerate(jobs): job.published_at = datetime.utcnow() - timedelta(days=index)
        db.commit()
        discovery = task(db, owner, payload={"automatic": True}, key="discovery")
        def assess(session, job, *args):
            return SimpleNamespace(state="new", assessment={"eligibility": "eligible"}, match_score=0)
        with patch("api.jobs.refresh", return_value={"status": "succeeded"}), patch("jobs.service.assess", side_effect=assess):
            result = execute(db, discovery)
            top = db.get(AutomationTask, result["preparation_task_ids"][0]); assert top.payload["job_id"] == jobs[0].id
            top.status = "succeeded"; db.commit()
            result = execute(db, discovery)
            second = db.get(AutomationTask, result["preparation_task_ids"][0]); assert second.payload["job_id"] == jobs[1].id
            assert execute(db, discovery)["preparation_task_ids"] == []
            assert db.query(AutomationTask).filter_by(kind="prepare", status="queued").count() == 1
            second.status = "failed"; db.commit()
            result = execute(db, discovery)
            third = db.get(AutomationTask, result["preparation_task_ids"][0]); assert third.payload["job_id"] == jobs[2].id


def test_automatic_task_paused_after_claim_is_rejected_before_network(queue):
    factory, owner, *_ = queue
    with factory() as db:
        automatic = task(db, owner, payload={"automatic": True})
        with patch("api.jobs.refresh") as refresh:
            with pytest.raises(HTTPException) as error: execute(db, automatic)
        assert error.value.status_code == 409
        refresh.assert_not_called()


def test_preparation_only_passes_previously_confirmed_compatible_skills(queue):
    factory, owner, _, job, master, _ = queue
    with factory() as db:
        db.add(ConfirmedSkill(user_id=owner.id, canonical="docker", name="Docker", category="Tools/Cloud")); db.commit()
        queued = queue_preparation(db, owner.id, job.id); db.commit()
        def analyze(request, session, user):
            run = LatexTailoringRun(user_id=user.id, master_id=request.master_id, job_description=request.job_description,
                label="QA", candidates=[{"canonical": "docker", "name": "Docker"}, {"canonical": "kubernetes", "name": "Kubernetes"}], status="analyzed")
            session.add(run); session.commit(); return {"id": run.id}
        def prepare(identifier, request, session, user):
            assert [(d.canonical, d.category) for d in request.confirmed_skills] == [("docker", "Tools/Cloud")]
            session.get(LatexTailoringRun, identifier).status = "ready"; session.commit()
        with patch("api.tailor.analyze", side_effect=analyze) as analyze_mock, patch("api.tailor.prepare", side_effect=prepare) as prepare_mock:
            result = execute(db, queued)
            result_again = execute(db, queued)
        assert result["awaiting_confirmation"] == ["Kubernetes"]
        assert result_again["run_id"] == result["run_id"]
        assert analyze_mock.call_count == prepare_mock.call_count == 1
        assert db.query(ConfirmedSkill).count() == 1


def test_changed_jd_stops_queued_preparation(queue):
    factory, owner, _, job, _, _ = queue
    with factory() as db:
        queued = queue_preparation(db, owner.id, job.id); db.commit()
        db.get(JobPosting, job.id).description_hash = "changed"; db.commit()
        with patch("api.tailor.analyze") as analyze:
            with pytest.raises(HTTPException) as error: execute(db, queued)
        assert error.value.status_code == 409
        analyze.assert_not_called()


def test_transient_failure_retries_three_times_then_stops(queue):
    factory, owner, *_ = queue
    with factory() as db: pending = task(db, owner, key="retry")
    with patch("automation.service.execute", side_effect=HTTPException(503, "Temporary source failure")):
        for attempt in range(1, 4):
            assert process_one(factory, "worker")
            with factory() as db:
                row = db.get(AutomationTask, pending.id)
                assert row.attempts == attempt
                assert row.status == ("queued" if attempt < 3 else "failed")
                assert row.lease_owner is None and row.lease_until is None
                row.available_at = datetime.utcnow() - timedelta(seconds=1); db.commit()
        assert not process_one(factory, "worker")


@pytest.mark.parametrize("header,minimum", [("120", 120), ("999999", 86400), ("invalid", 30)])
def test_retry_honors_bounded_server_delay(queue, header, minimum):
    factory, owner, *_ = queue
    with factory() as db: pending = task(db, owner, key="server-delay")
    before = datetime.utcnow()
    with patch("automation.service.execute", side_effect=HTTPException(503, "Rate limited", headers={"Retry-After": header})):
        assert process_one(factory, "worker")
    with factory() as db:
        row = db.get(AutomationTask, pending.id)
        assert row.status == "queued" and row.attempts == 1
        assert row.available_at >= before + timedelta(seconds=minimum)
        assert row.available_at <= datetime.utcnow() + timedelta(seconds=minimum + 1)


def test_all_failed_sources_propagate_longest_retry_after(queue):
    factory, owner, *_ = queue
    with factory() as db:
        pending = task(db, owner, key="all-failed")
        with patch("api.jobs.refresh", return_value={"status": "failed", "errors": [{"retry_after_seconds": 120}, {"retry_after_seconds": 300}]}):
            with pytest.raises(HTTPException) as error: execute(db, pending)
        assert error.value.headers["Retry-After"] == "300"
    assert retry_after_seconds("Sat, 31 Oct 2026 10:05:00 GMT", datetime(2026, 10, 31, 10)) == 300


@pytest.mark.parametrize("fails", [False, True])
def test_late_worker_cannot_overwrite_new_lease(queue, fails):
    factory, owner, *_ = queue
    with factory() as db: pending = task(db, owner, key="fence")
    def replaced_lease(db, current):
        db.commit()
        with factory() as other:
            row = other.get(AutomationTask, current.id); row.lease_owner = "new-worker"; row.attempts = 2; other.commit()
        if fails: raise HTTPException(503, "Old worker failed late")
        return {"old": "result"}
    with patch("automation.service.execute", side_effect=replaced_lease): assert process_one(factory, "old-worker")
    with factory() as db:
        row = db.get(AutomationTask, pending.id)
        assert row.status == "running" and row.lease_owner == "new-worker"
        assert row.attempts == 2 and row.result == {}


def test_retry_and_cancel_are_owned_and_state_limited(queue):
    factory, owner, other, _, _, client = queue
    with factory() as db:
        pending = task(db, owner, key="control")
        private = task(db, other, key="private")
    assert client.post(f"/automation/tasks/{private.id}/cancel").status_code == 404
    assert client.post(f"/automation/tasks/{pending.id}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/automation/tasks/{pending.id}/retry").json()["status"] == "queued"
    assert client.post(f"/automation/tasks/{pending.id}/retry").status_code == 409


@pytest.mark.parametrize("acquired", [False, True])
def test_worker_requires_leadership_and_stops_if_its_connection_is_lost(queue, acquired):
    # PostgreSQL owns a session advisory lock in a dedicated connection. A second
    # process must exit, and a leader whose connection fails must not reconnect
    # and process work without reacquiring leadership. SQLite fixture has no
    # claim-concurrency guarantee; this test models the PostgreSQL control path.
    from automation import worker
    factory, *_ = queue
    class Leadership:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, statement):
            query = str(statement)
            if "pg_try_advisory_lock" in query:
                return SimpleNamespace(scalar=lambda: acquired)
            if query == "SELECT 1":
                raise ConnectionError("Leadership connection lost")
            return SimpleNamespace(scalar=lambda: True)
    engine = SimpleNamespace(connect=lambda: Leadership(), dialect=SimpleNamespace(name="postgresql"))
    with patch.object(worker, "engine", engine), patch.object(worker, "SessionLocal", factory), patch.object(worker, "process_one") as process:
        worker.main()
    process.assert_not_called()
