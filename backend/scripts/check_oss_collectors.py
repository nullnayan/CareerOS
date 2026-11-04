"""Read-only doctor for Part 1 isolated OSS runtimes; never imports CareerOS."""
from __future__ import annotations

import json
import os
from pathlib import Path
import http.client
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "oss-tools" / "runtime"
SOURCES = RUNTIME / "sources"


def inspect(python: Path, code: str, env: dict[str, str] | None = None, timeout: int = 15) -> dict:
    if not python.is_file():
        return {"interpreter": str(python), "ok": False, "error": "interpreter missing"}
    try:
        safe_env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP") if os.environ.get(key)}
        safe_env["PATH"] = str(Path(python).parent)
        safe_env["PYTHONUTF8"] = "1"
        safe_env["PYTHONDONTWRITEBYTECODE"] = "1"
        if env:
            safe_env.update(env)
            for key in ("TEMP", "TMP"):
                if key not in safe_env and env.get("USERPROFILE"):
                    safe_env[key] = env["USERPROFILE"]
        result = subprocess.run([str(python), "-c", code], capture_output=True, text=True,
                                timeout=timeout, check=False, env=safe_env)
    except subprocess.TimeoutExpired:
        return {"interpreter": str(python), "ok": False, "error": "runtime inspection timed out"}
    except OSError:
        return {"interpreter": str(python), "ok": False, "error": "runtime inspection could not start"}
    try:
        value = json.loads(result.stdout)
    except (ValueError, json.JSONDecodeError):
        final_error = next((line.strip() for line in reversed(result.stderr.splitlines()) if line.strip()), "import check failed")
        value = {"error": final_error[-240:]}
    return {"interpreter": str(python), "ok": result.returncode == 0, **value}


def main() -> int:
    jobspy = ROOT / "backend" / ".source-tools-venv" / "Scripts" / "python.exe"
    envroot = RUNTIME / "environments"
    package_checks = {
        "jobspy": (jobspy, "import importlib.metadata as m, jobspy; print(__import__('json').dumps({'package':'python-jobspy','version':m.version('python-jobspy')}))"),
        "ats_scrapers": (envroot / "ats" / "Scripts" / "python.exe", "import importlib.metadata as m, ats_scrapers; print(__import__('json').dumps({'package':'ats-scrapers','version':m.version('ats-scrapers')}))"),
        "instahyre": (envroot / "instahyre" / "Scripts" / "python.exe", "import sys,json; sys.path.insert(0, r'" + str(SOURCES / "instahyre-scraper") + "'); import instahyre.jobs; print(json.dumps({'package':'instahyre-scraper','import':'ok'}))"),
        "internshala": (envroot / "internshala" / "Scripts" / "python.exe", "import sys,json; sys.path.insert(0, r'" + str(SOURCES / "internshala-scraper") + "'); import internshala.listings; print(json.dumps({'package':'internshala-scraper','import':'ok'}))"),
        "shine": (envroot / "shine" / "Scripts" / "python.exe", "import sys,json; sys.path.insert(0, r'" + str(SOURCES / "shine-scraper") + "'); import shine.jobs; print(json.dumps({'package':'shine-scraper','import':'ok'}))"),
        "crawl4ai": (envroot / "crawl4ai" / "Scripts" / "python.exe", "import importlib.metadata as m, crawl4ai; print(__import__('json').dumps({'package':'Crawl4AI','version':m.version('Crawl4AI'),'playwright':m.version('playwright')}))"),
    }
    checks = {name: inspect(python, code) for name, (python, code) in package_checks.items() if name != "crawl4ai"}
    with tempfile.TemporaryDirectory(prefix="oss-crawl4ai-doctor-", dir=RUNTIME) as doctor_tmp:
        checks["crawl4ai"] = inspect(envroot / "crawl4ai" / "Scripts" / "python.exe",
                                     package_checks["crawl4ai"][1],
                                     {"CRAWL4_AI_BASE_DIRECTORY": doctor_tmp,
                                      "USERPROFILE": doctor_tmp, "HOME": doctor_tmp,
                                      "TEMP": doctor_tmp, "TMP": doctor_tmp}, timeout=30)
    chromium = next(iter((RUNTIME / "browsers").glob("chromium-*/chrome-win64/chrome.exe")), None)
    headless_shell = next(iter((RUNTIME / "browsers").glob("chromium_headless_shell-*/chrome-headless-shell-win64/chrome-headless-shell.exe")), None)
    browser = {"ok": bool(chromium and headless_shell), "chromium": str(chromium) if chromium else None,
               "headless_shell": str(headless_shell) if headless_shell else None}
    model = os.environ.get("OSS_LOCAL_MODEL", "").strip()
    model_state = {"configured": bool(model), "available": False, "model": model[:100] if model else None}
    host = os.environ.get("OSS_OLLAMA_HOST", "http://127.0.0.1:11434").strip()
    if model and host in {"http://127.0.0.1:11434", "http://localhost:11434"}:
        try:
            connection = http.client.HTTPConnection("127.0.0.1" if "127.0.0.1" in host else "localhost", 11434, timeout=1.5)
            connection.request("GET", "/api/tags", headers={"Accept": "application/json"})
            response = connection.getresponse()
            data = json.loads(response.read(256 * 1024).decode("utf-8")) if response.status == 200 else {}
            connection.close()
            names = [str(item.get("name", "")) for item in data.get("models", []) if isinstance(item, dict)]
            model_state["available"] = any(name == model or name.startswith(model + ":") for name in names)
        except Exception:
            model_state["available"] = False
    report = {"status": "ok" if all(row.get("ok") for row in checks.values()) and browser.get("ok") else "incomplete",
              "runtimes": checks, "browser": browser, "local_model": model_state,
              "source_commits": {name: commit for name, commit in {
                  "JobSpy": "a606f9cf077c34f6ce6cbfcc76238f57b3c20671",
                  "ats-scrapers": "6b44a1badc9bfbf5cf176f75265cc5729e520e99",
                  "instahyre-scraper": "16a64f440e39a1545ea1322e21c6d8ef654a3358",
                  "internshala-scraper": "4755e7c83ec565e456384dffede100e9dfdc6a3d",
                  "shine-scraper": "ec9c0978b71ff502bf17e6b34fd0a64d150e410c",
                  "crawl4ai": "838869bdda93f25e6d50b3f50ae9577d9b19a586",
              }.items()},
              "side_effects": "No job sites, database, or CareerOS services were contacted or started."}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
