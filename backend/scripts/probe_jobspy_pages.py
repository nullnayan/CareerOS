"""Two-page signed-out smoke check; neutral query, no DB/profile or job ingestion."""
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from jobs.oss.coordinator import fetch
from jobs.connectors import SourceError

for source in ("naukri", "linkedin"):
    prefs = {"target_roles": ["Software Engineer"], "locations": ["India"], "country_code": "in", "max_posting_age_days": 7}
    seen = set()
    result = {"source": source, "checked_at": datetime.now(timezone.utc).isoformat(), "personal_data_used": False, "max_age_days": 7, "pages": []}
    for page in range(2):
        started = time.monotonic()
        try:
            snapshot = fetch(source, prefs)
            identities = {job.native_id for job in snapshot.jobs}
            result["pages"].append({"batch": page + 1, "jobs": len(snapshot.jobs), "new_ids": len(identities - seen),
                "companies": sorted({job.company for job in snapshot.jobs}), "complete_descriptions": sum(job.complete for job in snapshot.jobs),
                "experience_ranges": sorted({str(job.facts.get("experience_range")) for job in snapshot.jobs if job.facts.get("experience_range") is not None}),
                "more_pages": bool(snapshot.cursor), "warnings": snapshot.warnings, "seconds": round(time.monotonic() - started, 2)})
            seen |= identities
            if not snapshot.cursor: break
            prefs["_cursor"] = snapshot.cursor
            time.sleep(10)
        except SourceError as exc:
            result["pages"].append({"batch": page + 1, "error": str(exc), "reason": getattr(exc, "reason", None), "status": exc.status_code})
            break
    result["unique_jobs"] = len(seen)
    target = ROOT / "oss-tools/runtime/probes" / f"pagination-{source}.json"
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result), flush=True)
