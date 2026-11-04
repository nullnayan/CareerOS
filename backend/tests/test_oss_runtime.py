from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from jobs.oss.contracts import CollectorFailure, CollectorRequest, FailureReason, query_fingerprint
from jobs.oss import runtime
from jobs.oss.catalog import REPO_ROOT
from jobs.oss.runtime import run_bounded_json


def _alive(pid: int) -> bool:
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x00100000 | 0x1000, False, pid)
        if not handle:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0x102
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_timed_out_task_process_is_killed_and_failure_is_typed(tmp_path):
    pid_file = tmp_path / "owned-child.pid"
    code = "import os,pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)"
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "COMSPEC") if os.environ.get(key)}
    env["PATH"] = os.environ.get("PATH", "")
    env["PYTHONUTF8"] = "1"
    with pytest.raises(CollectorFailure) as error:
        run_bounded_json([sys.executable, "-c", code, str(pid_file)], {}, timeout=1.0,
                         env=env, cwd=tmp_path)
    assert error.value.reason is FailureReason.TIMEOUT
    pid = int(pid_file.read_text(encoding="utf-8"))
    assert not _alive(pid)


def test_cross_process_cancellation_kills_owned_scraper_before_timeout(tmp_path, monkeypatch):
    from jobs.oss import cancellation
    import time
    monkeypatch.setattr(cancellation, "RUNTIME_ROOT", tmp_path)
    value = cancellation.token("fixture", "task", "123")
    marker = cancellation.marker(value)
    marker.parent.mkdir(parents=True)
    pid_file = tmp_path / "running.pid"
    signal_code = "import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); deadline=time.monotonic()+5\nwhile not p.exists() and time.monotonic()<deadline: time.sleep(.02)\npathlib.Path(sys.argv[2]).touch()"
    signaller = subprocess.Popen([sys.executable, "-c", signal_code, str(pid_file), str(marker)])
    start = time.monotonic()
    try:
        with cancellation.scope([value]), pytest.raises(CollectorFailure) as error:
            run_bounded_json([sys.executable, "-c", "import os,pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)", str(pid_file)], {}, timeout=25, env=os.environ.copy())
        assert error.value.reason is FailureReason.CANCELLED
        assert time.monotonic() - start < 8
        assert not _alive(int(pid_file.read_text()))
    finally:
        signaller.wait(timeout=6)


def test_json_protocol_rejects_oversized_input_without_starting_process(tmp_path):
    with pytest.raises(CollectorFailure) as error:
        run_bounded_json([sys.executable, "-c", "print('{}')"], {"request": "x" * 200},
                         timeout=1, max_input_bytes=10, cwd=tmp_path)
    assert error.value.reason is FailureReason.INVALID_OUTPUT


def test_ats_runner_uses_its_installed_ats_environment(monkeypatch):
    request = CollectorRequest(
        source_id="stripe", tool="ats_scrapers", connection_key="stripe", generation=1,
        query_fingerprint=query_fingerprint("stripe", "ats_scrapers", "engineer", "remote", "US"),
        role="engineer", location="remote", country_code="US",
        entry_url="https://job-boards.greenhouse.io/stripe", max_results=1,
        max_details=0, deadline_seconds=20,
    )
    captured = {}

    def fake_run(argv, payload, **kwargs):
        captured["argv"] = argv
        captured["payload"] = payload
        return {"jobs": []}

    monkeypatch.setattr(runtime, "run_bounded_json", fake_run)
    runtime.invoke("ats_scrapers", request)
    assert Path(captured["argv"][0]) == REPO_ROOT / "oss-tools" / "runtime" / "environments" / "ats" / "Scripts" / "python.exe"
    assert captured["payload"]["source_id"] == "stripe"


def test_importing_oss_boundaries_does_not_contact_network_or_touch_database(tmp_path):
    code = """
import socket, urllib.request
def fail(*a, **k): raise AssertionError('network called during import')
socket.getaddrinfo = fail
socket.create_connection = fail
urllib.request.urlopen = fail
import jobs.oss.catalog, jobs.oss.contracts, jobs.oss.cursors
import jobs.oss.normalize, jobs.oss.runtime, jobs.oss.jobspy_adapter
import jobs.oss.ats_adapter, jobs.oss.omkar_adapter, jobs.oss.crawl_adapter
print('ok')
"""
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "COMSPEC") if os.environ.get(key)}
    env["PATH"] = os.environ.get("PATH", "")
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["DATABASE_URL"] = "sqlite://"
    env["TMP"] = str(tmp_path)
    env["TEMP"] = str(tmp_path)
    result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                            env=env, capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr[-1500:]
    assert result.stdout.strip() == "ok"
