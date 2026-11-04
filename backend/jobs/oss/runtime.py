"""Supervised JSON subprocess boundary for the isolated OSS runtimes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Mapping, Sequence

from .catalog import REPO_ROOT, RUNTIME_ROOT
from .contracts import CollectorFailure, CollectorRequest, FailureReason


MAX_INPUT_BYTES = 128 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_STDERR_BYTES = 96 * 1024
_RUNNERS = {
    "jobspy": "jobspy_runner.py",
    "ats_scrapers": "ats_runner.py",
    "instahyre": "omkar_runner.py",
    "internshala": "omkar_runner.py",
    "shine": "omkar_runner.py",
    "crawl4ai": "crawl4ai_runner.py",
}
_ENV_KEYS = ("SYSTEMROOT", "WINDIR", "COMSPEC")
_ENVIRONMENTS = {"ats_scrapers": "ats"}


def runtime_status():
    """Cheap presence check; explicit doctor performs import checks."""
    from .catalog import TOOL_VERSIONS
    result = {}
    for tool in _RUNNERS:
        python = (REPO_ROOT / "backend" / ".source-tools-venv" / "Scripts" / "python.exe" if tool == "jobspy" else
                  RUNTIME_ROOT / "environments" / _ENVIRONMENTS.get(tool, tool) / "Scripts" / "python.exe")
        result[tool] = {"installed": python.is_file(), "version": TOOL_VERSIONS[tool],
                        "check": "Interpreter presence only; run doctor for import health."}
    return result


def _safe_environment(tool: str) -> dict[str, str]:
    env = {key: os.environ[key] for key in _ENV_KEYS if os.environ.get(key)}
    system_root = env.get("SYSTEMROOT") or env.get("WINDIR")
    path_parts = []
    if system_root:
        path_parts.append(str(Path(system_root) / "System32"))
    env["PATH"] = os.pathsep.join(path_parts)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    isolated_home = RUNTIME_ROOT / "homes" / tool
    isolated_temp = RUNTIME_ROOT / "temp" / tool
    isolated_home.mkdir(parents=True, exist_ok=True)
    isolated_temp.mkdir(parents=True, exist_ok=True)
    env["USERPROFILE"] = str(isolated_home)
    env["HOME"] = str(isolated_home)
    env["TEMP"] = str(isolated_temp)
    env["TMP"] = str(isolated_temp)
    if tool == "crawl4ai":
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(RUNTIME_ROOT / "browsers")
        env["CRAWL4_AI_BASE_DIRECTORY"] = str(RUNTIME_ROOT / "crawl-data")
        model = os.environ.get("OSS_LOCAL_MODEL", "").strip()
        ollama_host = os.environ.get("OSS_OLLAMA_HOST", "http://127.0.0.1:11434").strip()
        if model and ollama_host in {"http://127.0.0.1:11434", "http://localhost:11434"}:
            env["OSS_LOCAL_MODEL"] = model[:100]
            env["OSS_OLLAMA_HOST"] = ollama_host
    return env


def _terminate_tree(process: subprocess.Popen[bytes]) -> None:
    """Terminate only the task-owned process tree, never a shared service."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=4, check=False,
                           creationflags=creationflags)
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass


def run_bounded_json(argv: Sequence[str], payload: Mapping[str, Any], *, timeout: float,
                     env: Mapping[str, str] | None = None, cwd: str | Path | None = None,
                     max_input_bytes: int = MAX_INPUT_BYTES,
                     max_output_bytes: int = MAX_OUTPUT_BYTES) -> dict[str, Any]:
    """Run a JSON process with hard deadline, output cap and process-tree cleanup."""
    from .cancellation import cancelled, check
    check()
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise CollectorFailure(FailureReason.INVALID_OUTPUT, "Collector input is not JSON serializable.") from None
    if len(encoded) > max_input_bytes:
        raise CollectorFailure(FailureReason.INVALID_OUTPUT, "Collector input exceeded its size limit.")
    if not argv or not Path(argv[0]).exists():
        raise CollectorFailure(FailureReason.RUNTIME_MISSING, "The isolated collector interpreter is not installed.")
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        process = subprocess.Popen(list(argv), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, cwd=str(cwd or REPO_ROOT),
                                   env=dict(env or {}), shell=False, **kwargs)
    except FileNotFoundError:
        raise CollectorFailure(FailureReason.RUNTIME_MISSING, "The isolated collector interpreter is not installed.") from None
    except OSError:
        raise CollectorFailure(FailureReason.RUNTIME_MISSING, "The isolated collector could not be started.") from None

    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    stdout_size = [0]
    stderr_size = [0]
    output_overflow = threading.Event()

    def reader(pipe, chunks: list[bytes], size: list[int], cap: int, output: bool) -> None:
        try:
            while True:
                data = pipe.read(8192)
                if not data:
                    break
                size[0] += len(data)
                if output and size[0] > cap:
                    output_overflow.set()
                    _terminate_tree(process)
                    continue
                if size[0] <= cap:
                    chunks.append(data)
        finally:
            try:
                pipe.close()
            except OSError:
                pass

    def write_input() -> None:
        try:
            assert process.stdin is not None
            process.stdin.write(encoded)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            try:
                if process.stdin:
                    process.stdin.close()
            except OSError:
                pass

    assert process.stdout is not None and process.stderr is not None
    threads = [threading.Thread(target=reader, args=(process.stdout, stdout_chunks, stdout_size, max_output_bytes, True), daemon=True),
               threading.Thread(target=reader, args=(process.stderr, stderr_chunks, stderr_size, MAX_STDERR_BYTES, False), daemon=True),
               threading.Thread(target=write_input, daemon=True)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + max(0.1, min(float(timeout), 120.0))
    deadline_hit = False
    try:
        while process.poll() is None and time.monotonic() < deadline and not output_overflow.is_set() and not cancelled():
            time.sleep(0.05)
        if process.poll() is None:
            deadline_hit = time.monotonic() >= deadline
            _terminate_tree(process)
    except BaseException:
        _terminate_tree(process)
        raise
    for thread in threads:
        thread.join(timeout=3)
    check()
    if any(thread.is_alive() for thread in threads):
        _terminate_tree(process)
        raise CollectorFailure(FailureReason.TIMEOUT, "Collector process cleanup exceeded its deadline.")
    if output_overflow.is_set():
        raise CollectorFailure(FailureReason.INVALID_OUTPUT, "Collector output exceeded its size limit.")
    if deadline_hit:
        raise CollectorFailure(FailureReason.TIMEOUT, "Collector exceeded its deadline; its owned process tree was terminated.")
    raw = b"".join(stdout_chunks)
    if not raw:
        raise CollectorFailure(FailureReason.INVALID_OUTPUT, "Collector returned no JSON output.")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CollectorFailure(FailureReason.INVALID_OUTPUT, "Collector returned malformed JSON.") from None
    if not isinstance(value, dict):
        raise CollectorFailure(FailureReason.INVALID_OUTPUT, "Collector output must be a JSON object.")
    if value.get("failure"):
        failure = value["failure"]
        if not isinstance(failure, dict):
            raise CollectorFailure(FailureReason.INVALID_OUTPUT, "Collector failure record is malformed.")
        try:
            raise CollectorFailure(failure.get("reason", FailureReason.TRANSPORT),
                                   failure.get("safe_message", "Source collection failed."),
                                   failure.get("status_code"), failure.get("retry_after_seconds"))
        except ValueError:
            raise CollectorFailure(FailureReason.INVALID_OUTPUT, "Collector failure record is invalid.") from None
    if process.returncode not in (0, None):
        raise CollectorFailure(FailureReason.TRANSPORT, "Collector exited before returning a valid result.")
    return value


def invoke(tool: str, request: CollectorRequest) -> dict[str, Any]:
    if tool not in _RUNNERS or request.tool != tool:
        raise CollectorFailure(FailureReason.UNSUPPORTED, "No isolated runner is registered for this request.")
    env_name = "jobspy" if tool == "jobspy" else _ENVIRONMENTS.get(tool, tool)
    python = (REPO_ROOT / "backend" / ".source-tools-venv" / "Scripts" / "python.exe"
              if tool == "jobspy" else RUNTIME_ROOT / "environments" / env_name / "Scripts" / "python.exe")
    runner = Path(__file__).resolve().parent / "runners" / _RUNNERS[tool]
    if not runner.is_file():
        raise CollectorFailure(FailureReason.RUNTIME_MISSING, "The collector runner file is missing.")
    return run_bounded_json([str(python), str(runner)], request.to_payload(),
                            timeout=request.deadline_seconds, env=_safe_environment(tool), cwd=REPO_ROOT)
