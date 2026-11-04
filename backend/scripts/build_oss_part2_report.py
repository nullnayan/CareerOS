"""Record code/probe evidence without opening a database or searching jobs."""
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from jobs.oss.coordinator import catalog

baseline = json.loads((ROOT / "OSS_SOURCE_COVERAGE.json").read_text(encoding="utf-8"))
baseline["part"] = "Part 2 OSS integration coverage; connection state is not inferred"
baseline["generated_utc"] = datetime.now(timezone.utc).isoformat()
baseline["scope_note"] = "Part 1 evidence retained. Legacy probes do not verify OSS. Runtime/source setup is separate from live access. No personal database read."
baseline["oss_connection_options"] = catalog()
baseline["part2_probe_artifact"] = "oss-tools/runtime/probes/part2-shine-stripe.json"
baseline["part2_notes"] = [
    "Shine and Stripe each returned one complete description in bounded technical probes.",
    "ATS catalogues now page through a one-hour bounded local snapshot; no full-board refetch per continuation.",
    "Naukri and LinkedIn were each checked through two signed-out 20-result batches: 39 and 40 distinct jobs respectively, across many companies. These are neutral query samples, not fresher coverage totals.",
    "Instahyre works through the local upstream's direct-access option; the earlier proxy-only finding was incorrect.",
    "Wellfound and Internshala retain internal terms-review gates; Superset has no verified public route. These are not blanket login requirements for public job searches.",
    "Other Crawl4AI/company profiles remain partial or unverified. A saved profile is not verified search coverage.",
]
baseline["latest_public_probe_evidence"] = [json.loads(path.read_text(encoding="utf-8"))
    for pattern in ("completion-*.json", "pagination-*.json")
    for path in sorted((ROOT / "oss-tools/runtime/probes").glob(pattern))]
(ROOT / "OSS_DISCOVERY_COVERAGE_PART2.json").write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

paths = [
    "backend/core/config.py", "backend/jobs/engine.py", "backend/jobs/connectors.py", "backend/jobs/adapters.py",
    "backend/jobs/scheduling.py", "backend/jobs/verification.py", "backend/api/jobs.py", "backend/automation/service.py",
    "backend/jobs/oss/coordinator.py", "backend/jobs/oss/runtime.py", "backend/jobs/oss/omkar_adapter.py",
    "backend/jobs/oss/ats_adapter.py", "backend/jobs/oss/crawl_adapter.py", "backend/jobs/oss/crawl_extract.py",
    "backend/jobs/oss/runners/omkar_runner.py", "backend/jobs/oss/runners/ats_runner.py", "backend/jobs/oss/runners/crawl4ai_runner.py",
    "backend/tests/conftest.py", "backend/tests/test_oss_integration.py", "backend/tests/test_oss_isolated_runners.py",
    "frontend/app/jobs/oss-connections-panel.tsx", "frontend/app/jobs/page.tsx", "frontend/app/lib/jobs.ts",
    "backend/scratch/build_oss_ui_check.py", "backend/scratch/verify_oss_discovery_ui.py", "backend/scripts/build_oss_part2_report.py",
    "OSS_DISCOVERY_COVERAGE_PART2.json", "OSS_DISCOVERY_IMPLEMENTATION_REPORT.md", "OSS_DISCOVERY_OPERATING_GUIDE.md",
    "backend/jobs/oss/cancellation.py", "backend/jobs/search_control.py", "backend/api/automation.py",
    "backend/jobs/schemas.py", "backend/jobs/matching.py", "backend/jobs/service.py",
    "backend/jobs/oss/contracts.py", "backend/jobs/oss/normalize.py", "backend/jobs/oss/jobspy_adapter.py",
    "backend/jobs/oss/runners/jobspy_runner.py", "backend/scripts/probe_jobspy_pages.py",
    "backend/tests/test_oss_search_filters.py", "backend/tests/test_oss_runtime.py", "backend/tests/test_automation.py",
    "backend/tests/test_search_architecture.py", "frontend/app/automation/page.tsx", "SEARCH_PIPELINE_FIXES.md",
]
paths += [str(path.relative_to(ROOT)).replace("\\", "/") for path in sorted((ROOT / "backend/jobs/oss/profiles").glob("*.json"))]
files = [{"path": path, "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()} for path in paths if (ROOT / path).is_file()]
(ROOT / "OSS_SOL_CHANGED_FILES.json").write_text(json.dumps({"files": files, "note": "Final file hashes; workspace has no git diff. Excludes generated runtimes/builds/logs."}, indent=2) + "\n", encoding="utf-8")
