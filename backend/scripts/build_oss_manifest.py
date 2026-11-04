"""Create the OSS collector provenance manifest from pinned local checkouts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "oss-tools" / "runtime"
SOURCES = RUNTIME / "sources"
LOCKS = ROOT / "oss-tools" / "locks"
LICENSES = ROOT / "oss-tools" / "licenses"

TOOLS = [
    {"id": "jobspy", "name": "python-jobspy", "repository": "https://github.com/speedyapply/JobSpy",
     "directory": "JobSpy", "commit": "a606f9cf077c34f6ce6cbfcc76238f57b3c20671",
     "distribution": "python-jobspy", "lock": "jobspy-py311.lock.txt", "license": "JobSpy-LICENSE.txt",
     "environment": ROOT / "backend" / ".source-tools-venv", "interpreter": ROOT / "backend" / ".source-tools-venv" / "Scripts" / "python.exe",
     "install_mode": "editable pinned local source in isolated non-production venv"},
    {"id": "ats_scrapers", "name": "ats-scrapers", "repository": "https://github.com/kalil0321/ats-scrapers",
     "directory": "ats-scrapers", "commit": "6b44a1badc9bfbf5cf176f75265cc5729e520e99",
     "distribution": "ats-scrapers", "lock": "ats-py311.lock.txt", "license": "ats-scrapers-LICENSE.txt",
     "environment": RUNTIME / "environments" / "ats", "interpreter": RUNTIME / "environments" / "ats" / "Scripts" / "python.exe",
     "install_mode": "editable pinned local source in dedicated isolated venv; unnecessary stealth extras omitted"},
    {"id": "instahyre", "name": "instahyre-scraper", "repository": "https://github.com/omkarcloud/instahyre-scraper",
     "directory": "instahyre-scraper", "commit": "16a64f440e39a1545ea1322e21c6d8ef654a3358",
     "distribution": None, "lock": "instahyre-py311.lock.txt", "license": "instahyre-scraper-LICENSE.txt",
     "environment": RUNTIME / "environments" / "instahyre", "interpreter": RUNTIME / "environments" / "instahyre" / "Scripts" / "python.exe",
     "install_mode": "pinned requirements in dedicated venv; runner imports pinned local source tree"},
    {"id": "internshala", "name": "internshala-scraper", "repository": "https://github.com/omkarcloud/internshala-scraper",
     "directory": "internshala-scraper", "commit": "4755e7c83ec565e456384dffede100e9dfdc6a3d",
     "distribution": None, "lock": "internshala-py311.lock.txt", "license": "internshala-scraper-LICENSE.txt",
     "environment": RUNTIME / "environments" / "internshala", "interpreter": RUNTIME / "environments" / "internshala" / "Scripts" / "python.exe",
     "install_mode": "pinned requirements in dedicated venv; runner imports pinned local source tree"},
    {"id": "shine", "name": "shine-scraper", "repository": "https://github.com/omkarcloud/shine-scraper",
     "directory": "shine-scraper", "commit": "ec9c0978b71ff502bf17e6b34fd0a64d150e410c",
     "distribution": None, "lock": "shine-py311.lock.txt", "license": "shine-scraper-LICENSE.txt",
     "environment": RUNTIME / "environments" / "shine", "interpreter": RUNTIME / "environments" / "shine" / "Scripts" / "python.exe",
     "install_mode": "pinned requirements in dedicated venv; runner imports pinned local source tree"},
    {"id": "crawl4ai", "name": "Crawl4AI", "repository": "https://github.com/unclecode/crawl4ai",
     "directory": "crawl4ai", "commit": "838869bdda93f25e6d50b3f50ae9577d9b19a586",
     "distribution": "Crawl4AI", "lock": "crawl4ai-py311.lock.txt", "license": "crawl4ai-LICENSE.txt",
     "environment": RUNTIME / "environments" / "crawl4ai", "interpreter": RUNTIME / "environments" / "crawl4ai" / "Scripts" / "python.exe",
     "install_mode": "editable pinned local source in isolated venv; Playwright Chromium revision 1248"},
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_revision(path: Path) -> str:
    result = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                            check=True, capture_output=True, text=True, timeout=10)
    return result.stdout.strip()


def package_versions(interpreter: Path, names: list[str]) -> dict[str, str | None]:
    code = "import importlib.metadata as m,json; names=" + repr(names) + "; out={};\n" \
           "for n in names:\n" \
           " try: out[n]=m.version(n)\n" \
           " except m.PackageNotFoundError: out[n]=None\n" \
           "print(json.dumps(out))"
    result = subprocess.run([str(interpreter), "-c", code], check=True,
                            capture_output=True, text=True, timeout=20)
    return json.loads(result.stdout)


def main() -> int:
    rows = []
    for spec in TOOLS:
        source = SOURCES / spec["directory"]
        lock = LOCKS / spec["lock"]
        license_path = LICENSES / spec["license"]
        interpreter: Path = spec["interpreter"]
        if not source.is_dir() or not (source / ".git").is_dir():
            raise FileNotFoundError(f"Pinned source checkout missing: {source}")
        actual_commit = git_revision(source)
        if actual_commit != spec["commit"]:
            raise RuntimeError(f"Pinned commit mismatch for {spec['id']}: {actual_commit}")
        for path in (lock, license_path, interpreter):
            if not path.exists():
                raise FileNotFoundError(path)
        names = [spec["distribution"]] if spec["distribution"] else []
        if spec["id"] == "crawl4ai":
            names.append("playwright")
        versions = package_versions(interpreter, names)
        lock_lines = [line for line in lock.read_text(encoding="utf-8").splitlines()
                      if line.strip() and not line.lstrip().startswith("#")]
        rows.append({
            "id": spec["id"], "upstream_name": spec["name"], "repository": spec["repository"],
            "source_checkout": str(source), "pinned_commit": spec["commit"], "actual_commit": actual_commit,
            "commit_matches": True, "distribution_versions": versions,
            "environment": str(spec["environment"]), "interpreter": str(interpreter),
            "isolated_from_backend_production_venv": True, "install_mode": spec["install_mode"],
            "lock_file": str(lock.relative_to(ROOT)).replace("\\", "/"), "lock_sha256": sha256(lock),
            "locked_requirement_count": len(lock_lines),
            "license_file": str(license_path.relative_to(ROOT)).replace("\\", "/"),
            "license_sha256": sha256(license_path), "installed": True,
        })

    browser_dir = RUNTIME / "browsers"
    browser_files = [
        browser_dir / "chromium-1248" / "chrome-win64" / "chrome.exe",
        browser_dir / "chromium_headless_shell-1248" / "chrome-headless-shell-win64" / "chrome-headless-shell.exe",
    ]
    browser = []
    for path in browser_files:
        if not path.is_file():
            raise FileNotFoundError(path)
        browser.append({"path": str(path), "sha256": sha256(path), "size_bytes": path.stat().st_size})

    manifest = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "python": "3.11",
        "tools": rows,
        "browser_runtime": {"playwright_version": "1.64.1", "chromium_revision": "1248",
                            "binaries": browser, "isolated_runtime": True},
        "runtime_root": str(RUNTIME),
        "ignore_rule": "/oss-tools/runtime/",
    }
    destination = ROOT / "oss-tools" / "manifest.json"
    destination.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(destination), "tools": len(rows),
                      "locks_and_licenses_hashed": True,
                      "browser_binaries_hashed": len(browser)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
