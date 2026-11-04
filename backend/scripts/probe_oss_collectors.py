"""Run only the bounded neutral Part 1 checks listed below; no personal queries."""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "oss-tools" / "runtime"
os.environ["DATABASE_URL"] = "sqlite://"
sys.path.insert(0, str(ROOT / "backend"))

from jobs.oss.catalog import TOOL_VERSIONS
from jobs.oss.contracts import CollectorFailure, CollectorRequest, query_fingerprint
from jobs.oss import ats_adapter, crawl_adapter, omkar_adapter


def _request(source_id: str, tool: str, location: str, country: str, *, entry_url: str | None = None,
             max_details: int = 0, seconds: int = 35) -> CollectorRequest:
    role = "software engineer"
    return CollectorRequest(source_id=source_id, tool=tool, connection_key=source_id,
                            generation=1, query_fingerprint=query_fingerprint(source_id, tool, role, location, country),
                            role=role, location=location, country_code=country,
                            entry_url=entry_url, max_results=1, max_details=max_details,
                            deadline_seconds=seconds)


def _shape(batch) -> dict:
    rows = batch.jobs
    if not rows:
        return {"job_count": 0, "representative_fields": []}
    row = rows[0]
    return {"job_count": len(rows), "representative_fields": {
        "title": bool(row.title), "company": bool(row.company), "location": bool(row.location),
        "source_url": bool(row.facts.get("source_url")),
        "original_application_url": bool(row.facts.get("original_application_url")),
        "description_present": bool(row.description),
        "description_complete": row.complete,
        "salary_fields": sorted(key for key in row.facts if key.startswith("salary_") or key == "stipend"),
    }}


def _probe(label: str, adapter, request: CollectorRequest, official_url: str, tool: str) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    try:
        batch = adapter.collect(request)
        return {"id": label, "tool": tool, "tool_version": batch.tool_version or TOOL_VERSIONS.get(tool, "unknown"),
                "official_url": official_url, "started_utc": started, "outcome": batch.coverage,
                "request_count": batch.request_count, "sample_shape": _shape(batch),
                "description_complete_count": sum(row.complete for row in batch.jobs),
                "pagination_observed": bool(batch.next_cursor), "warnings": batch.warnings[:12],
                "query": {"role": request.role, "location": request.location, "country_code": request.country_code,
                          "max_results": request.max_results, "max_details": request.max_details}}
    except CollectorFailure as exc:
        return {"id": label, "tool": tool, "tool_version": TOOL_VERSIONS.get(tool, "unknown"),
                "official_url": official_url, "started_utc": started, "outcome": exc.reason.value,
                "request_count": 0 if label in {"wellfound", "superset", "instahyre", "internshala_jobs"} else None,
                "failure": exc.to_dict(), "sample_shape": {"job_count": 0},
                "description_complete_count": 0, "pagination_observed": False,
                "query": {"role": request.role, "location": request.location, "country_code": request.country_code,
                          "max_results": request.max_results, "max_details": request.max_details}}
    except Exception:
        return {"id": label, "tool": tool, "tool_version": TOOL_VERSIONS.get(tool, "unknown"),
                "official_url": official_url, "started_utc": started, "outcome": "transport",
                "request_count": None, "failure": {"reason": "transport", "safe_message": "Probe failed before a normalized batch was returned."},
                "sample_shape": {"job_count": 0}, "description_complete_count": 0,
                "pagination_observed": False,
                "query": {"role": request.role, "location": request.location, "country_code": request.country_code,
                          "max_results": request.max_results, "max_details": request.max_details}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", dest="only", help="Probe one source id; may be repeated.")
    parser.add_argument("--output", help="Artifact path relative to the repository root.")
    args = parser.parse_args()
    only = set(args.only or [])
    allowed = {"shine", "unstop", "cutshort", "foundit", "cuvette", "cognizant", "tcs",
               "infosys", "wipro", "accenture", "deloitte", "greenhouse-stripe", "wellfound",
               "superset", "instahyre", "internshala_jobs"}
    unknown = only - allowed
    if unknown:
        parser.error("unknown source id(s): " + ", ".join(sorted(unknown)))
    def selected(source_id: str) -> bool:
        return not only or source_id in only

    probes = []
    if selected("shine"):
        probes.append(_probe("shine", omkar_adapter, _request("shine", "shine", "Bengaluru", "IN", max_details=1),
                             "https://www.shine.com/job-search/", "shine"))
    for source_id, url in (("unstop", "https://unstop.com/jobs"),
                           ("cutshort", "https://cutshort.io/jobs"),
                           ("foundit", "https://www.foundit.in/srp/results"),
                           ("cuvette", "https://cuvette.tech/jobs")):
        if not selected(source_id):
            continue
        request = _request(source_id, "crawl4ai", "Bengaluru", "IN", entry_url=url, max_details=1)
        probes.append(_probe(source_id, crawl_adapter, request, url, "crawl4ai"))

    # The six highest-priority company URLs come from the existing dated
    # official-careers review. These one-page checks do not confirm an ATS slug.
    companies = (
        ("cognizant", "https://careers.cognizant.com/"),
        ("tcs", "https://www.tcs.com/careers/india"),
        ("infosys", "https://www.infosys.com/careers/apply.html"),
        ("wipro", "https://careers.wipro.com/"),
        ("accenture", "https://www.accenture.com/in-en/careers"),
        ("deloitte", "https://www.deloitte.com/global/en/careers/job-search.html"),
    )
    for source_id, url in companies:
        if not selected(source_id):
            continue
        request = _request(source_id, "crawl4ai", "India", "IN", entry_url=url, max_details=1)
        probes.append(_probe(source_id, crawl_adapter, request, url, "crawl4ai"))

    # One documented company-published Greenhouse board checks the local ATS
    # adapter's actual fetch path and its one-description detail budget.
    stripe_url = "https://job-boards.greenhouse.io/stripe"
    if selected("greenhouse-stripe"):
        probes.append(_probe("greenhouse-stripe", ats_adapter,
                             _request("stripe", "ats_scrapers", "remote", "US", entry_url=stripe_url,
                                      max_details=1, seconds=50), stripe_url, "ats_scrapers"))

    # These local checks are intentionally zero-network because the review or
    # upstream code requires access that Part 1 does not have.
    for source_id, tool, adapter, url in (
        ("wellfound", "crawl4ai", crawl_adapter, "https://wellfound.com/jobs"),
        ("superset", "crawl4ai", crawl_adapter, "https://app.joinsuperset.com/"),
        ("instahyre", "instahyre", omkar_adapter, "https://www.instahyre.com/"),
        ("internshala_jobs", "internshala", omkar_adapter, "https://internshala.com/jobs/"),
    ):
        if not selected(source_id):
            continue
        request = _request(source_id, tool, "Bengaluru", "IN", entry_url=url)
        probes.append(_probe(source_id, adapter, request, url, tool))

    report = {"probe_run_utc": datetime.now(timezone.utc).isoformat(),
              "purpose": "One bounded neutral technical query; results are not a personal search or production coverage claim.",
              "artifacts_redacted": True,
              "probes": probes,
              "source_policy": "No accounts, cookies, CAPTCHA or challenge bypass, proxies, paid APIs, RapidAPI, hosted LLMs, or personal data."}
    destination = ROOT / args.output if args.output else RUNTIME / "probes" / "part1-probes-2026-11-03.json"
    if not destination.resolve().is_relative_to(RUNTIME.resolve()):
        raise ValueError("Probe artifacts must stay inside the ignored oss-tools/runtime directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(destination), "count": len(probes),
                      "outcomes": {item["id"]: item["outcome"] for item in probes}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
