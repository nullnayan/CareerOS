"""Bounded neutral verification only; never imports application DB/settings."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from jobs.oss.contracts import CollectorRequest, CollectorFailure, query_fingerprint
from jobs.oss.coordinator import specification
from jobs.oss import jobspy_adapter, ats_adapter, crawl_adapter, omkar_adapter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+")
    args = parser.parse_args()
    for key in args.sources:
        row = specification(key)
        country = {"zip_recruiter": "US", "bayt": "AE", "bdjobs": "BD", "hellowork": "FR"}.get(key, "IN")
        location = {"US": "United States", "AE": "Dubai", "BD": "Dhaka", "FR": "Paris"}.get(country, "India")
        role = "software engineer"
        tool = row["tool"]
        request = CollectorRequest(key, tool, key, 0, query_fingerprint(key, tool, role, location, country),
            role, location, country, entry_url=row["url"], max_results=1, max_details=1, deadline_seconds=45)
        started = time.monotonic()
        result = {"source": key, "tool": tool, "entry_url": row["url"], "query": {"role": role, "location": location, "country": country},
                  "checked_at": datetime.now(timezone.utc).isoformat(), "personal_data_used": False}
        try:
            collector = {"jobspy": jobspy_adapter, "ats_scrapers": ats_adapter, "crawl4ai": crawl_adapter, "instahyre": omkar_adapter}[tool]
            batch = collector.collect(request)
            result.update(outcome=batch.coverage, jobs=len(batch.jobs), complete_descriptions=sum(j.complete for j in batch.jobs),
                          continuation=bool(batch.next_cursor), requests=batch.request_count, warnings=batch.warnings,
                          version=batch.tool_version)
        except CollectorFailure as exc: result.update(outcome=exc.reason.value, message=exc.safe_message, status=exc.status_code)
        result["elapsed_seconds"] = round(time.monotonic() - started, 2)
        out = ROOT / "oss-tools" / "runtime" / "probes" / ("completion-" + key + ".json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result), flush=True)


if __name__ == "__main__": main()
