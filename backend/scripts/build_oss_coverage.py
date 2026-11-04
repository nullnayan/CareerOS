"""Build the Part 1 source ledger from the installed inventory and probe evidence.

This script reads only static source metadata and redacted OSS probe artifacts. It
does not open a CareerOS database, import personal settings, or contact any site.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
RUNTIME = ROOT / "oss-tools" / "runtime"
os.environ["DATABASE_URL"] = "sqlite://"
sys.path.insert(0, str(BACKEND))

from jobs.access_review import COMMUNITY_SITES, REVIEWS  # noqa: E402
from jobs.directory import company_directory  # noqa: E402
from jobs.oss.catalog import JOBSPY_SITES, OMKAR_SITES, PLATFORM_URLS, TOOL_VERSIONS  # noqa: E402
from jobs.registry import PLATFORMS, ENTERPRISE, source_register  # noqa: E402


REPORT = ROOT / "SOURCE_TOOLS_IMPLEMENTATION_REPORT.md"
PROBE_FILES = (
    RUNTIME / "probes" / "part1-probes-2026-11-03.json",
    RUNTIME / "probes" / "part1-greenhouse-stripe-followup.json",
    RUNTIME / "probes" / "part1-shine-guard-followup.json",
)
URL_CELL = re.compile(r"^\| ([^|]+) \| \[Careers\]\((https?://[^)]+)\) \| ([^|]+) \|$")

PLATFORM_TOOLS = {
    "LinkedIn": "jobspy", "Naukri.com": "jobspy", "Indeed": "jobspy",
    "Glassdoor": "jobspy", "ZipRecruiter": "jobspy", "Bayt": "jobspy",
    "BDJobs": "jobspy", "HelloWork": "jobspy",
    "Unstop": "crawl4ai", "Foundit": "crawl4ai", "Cutshort": "crawl4ai",
    "Cuvette": "crawl4ai", "Wellfound": "crawl4ai", "Instahyre": "instahyre",
    "Internshala": "internshala", "Shine": "shine",
}
NOT_CATALOGUES = {"HackerEarth", "HackerRank", "CodeChef"}
EXISTING_API_NAMES = {"Greenhouse", "Lever", "Ashby", "SmartRecruiters", "Workable",
                      "Remotive", "Jobicy", "Himalayas"}
PROFILE_IDS = {
    "Unstop": "unstop", "Wellfound": "wellfound", "Cutshort": "cutshort",
    "Foundit": "foundit", "Cuvette": "cuvette", "Superset": "superset",
    "Cognizant": "cognizant", "TCS": "tcs", "Infosys": "infosys",
    "Wipro": "wipro", "Accenture": "accenture", "Deloitte": "deloitte",
    "Internshala": "internshala_jobs",
}
EXTRA_TARGETS = {
    "superset": ("Superset", "https://app.joinsuperset.com/", "India; campus recruiting; no public catalogue route verified."),
}
EMPLOYER_URLS: dict[str, str] = {}
for line in REPORT.read_text(encoding="utf-8").splitlines():
    match = URL_CELL.match(line.strip())
    if match:
        EMPLOYER_URLS[match.group(1).strip()] = match.group(2)


def _load_probe_index() -> tuple[dict[str, dict], list[str]]:
    index: dict[str, dict] = {}
    found = []
    for path in PROBE_FILES:
        if not path.is_file():
            continue
        found.append(path.relative_to(ROOT).as_posix())
        payload = json.loads(path.read_text(encoding="utf-8"))
        for probe in payload.get("probes", []):
            source_id = str(probe.get("id") or "")
            if probe.get("failure") and source_id not in {"wellfound", "superset", "instahyre", "internshala_jobs", "greenhouse-stripe"}:
                # Failed browser processes cannot report their in-page request
                # total. Never turn an unobserved total into a zero count.
                probe["request_count"] = None
                probe["request_count_note"] = "Unknown because the runner failed before returning a batch."
            if source_id and (source_id not in index or probe.get("started_utc", "") > index[source_id].get("started_utc", "")):
                index[source_id] = dict(probe, artifact=path.relative_to(ROOT).as_posix())
    # The first bounded run accidentally selected a nonexistent ATS runtime key.
    # Keep that failed attempt for audit while the later isolated retry is current.
    primary = PROBE_FILES[0]
    followup = PROBE_FILES[1]
    if primary.is_file() and followup.is_file():
        old = next((row for row in json.loads(primary.read_text(encoding="utf-8")).get("probes", [])
                    if row.get("id") == "greenhouse-stripe"), None)
        if old:
            index["greenhouse-stripe"]["previous_attempt"] = {
                "outcome": old.get("outcome"), "failure": old.get("failure"),
                "started_utc": old.get("started_utc"), "artifact": primary.relative_to(ROOT).as_posix(),
            }
    return index, found


def _tool_version(tool: str | None) -> str:
    return TOOL_VERSIONS.get(tool or "", "not installed or not selected")


def _probe_detail(probe: dict | None) -> dict | None:
    if not probe:
        return None
    return {key: probe.get(key) for key in (
        "id", "tool", "tool_version", "started_utc", "outcome", "request_count",
        "sample_shape", "description_complete_count", "pagination_observed", "warnings", "failure",
        "query", "artifact", "request_count_note", "previous_attempt",
    ) if key in probe}


def _state_for_platform(name: str, tool: str | None, probe: dict | None,
                        base: dict) -> tuple[str, str]:
    if name == "Adzuna":
        return "excluded-paid", "Excluded from free expansion; existing historical settings were left unchanged."
    if name in NOT_CATALOGUES:
        return "not-a-job-catalogue", "The reviewed product is an assessment/challenge service, not a candidate vacancy catalogue."
    if name in EXISTING_API_NAMES:
        return "live-verified", "Existing CareerOS API/feed implementation has prior probe evidence dated 2026-11-01; Part 1 did not change its route."
    if name in {"Workday", "Oracle Recruiting", "Taleo", "SAP SuccessFactors", "iCIMS"}:
        return "installed", "Part 1 ATS runtime is installed and exercised against a Greenhouse board; this vendor category has no tested employer tenant/feed mapping."
    if probe:
        outcome = probe.get("outcome")
        count = (probe.get("sample_shape") or {}).get("job_count", 0)
        if outcome == "login_required":
            return "login-required", str((probe.get("failure") or {}).get("safe_message") or "No public search route was established.")
        if outcome in {"blocked", "timeout", "rate_limited"}:
            return "blocked", str((probe.get("failure") or {}).get("safe_message") or "Bounded technical probe was blocked or timed out.")
        if count:
            return "partial", "One bounded result page returned normalized records; pagination/exhaustiveness is not established."
        return "planned", "A bounded probe ran, but no verified job result or exhaustive empty-result proof was obtained."
    if name in COMMUNITY_SITES:
        return "blocked", "JobSpy support is not permission; the access review requires an approved export/feed before unattended collection."
    if name in {"FreshersNow", "Wellfound", "Internshala"}:
        return "blocked", "The source access review requires express permission or an authorized export before automated extraction."
    if name == "National Career Service":
        return "blocked", "Requires NCS partner-approved vacancy export; jobseeker browsing is not partner authorization."
    return "planned", "No permitted free feed or tested public search route is established; obtain the exact prerequisite in access_review before implementation."


def _source_url(entry: dict) -> tuple[str | None, str]:
    name = entry["name"]
    if name in PLATFORM_URLS:
        return PLATFORM_URLS[name], "official_source_entry"
    if name in REVIEWS:
        return REVIEWS[name][0], "official_review_or_vendor_documentation"
    return entry.get("documentation_url"), "official_vendor_documentation"


def build_sources(probes: dict[str, dict]) -> list[dict]:
    result = []
    entries = source_register()
    for original in entries:
        entry = dict(original)
        name = entry["name"]
        source_id = entry["id"]
        tool = ("existing_public_api" if name in EXISTING_API_NAMES else
                "ats_scrapers" if name in {"Workday", "Oracle Recruiting", "Taleo", "SAP SuccessFactors", "iCIMS"} else
                PLATFORM_TOOLS.get(name))
        if name in COMMUNITY_SITES:
            site_id = COMMUNITY_SITES[name]
            tool = "jobspy"
            capability = JOBSPY_SITES.get(site_id)
        else:
            capability = OMKAR_SITES.get("internshala_jobs" if name == "Internshala" else "shine" if name == "Shine" else "instahyre" if name == "Instahyre" else "")
        profile_id = PROFILE_IDS.get(name)
        probe = probes.get(profile_id or source_id)
        state, reason = _state_for_platform(name, tool, probe, entry)
        url, url_kind = _source_url(entry)
        preferred = tool or "unassigned"
        runtime_version = (_tool_version(tool) if tool and tool != "existing_public_api" else
                           "Existing CareerOS API/feed adapters; see SOURCE_TOOLS_IMPLEMENTATION_REPORT.md" if tool else
                           "No collector runtime assigned")
        scope = capability.country_scope if capability else entry.get("geography") or "Unverified; no country coverage claim."
        if entry.get("scope") == "employer_configured":
            scope = "Employer-configured feed; exact tenant/programme is required."
        probe_value = _probe_detail(probe)
        if not probe_value and entry.get("observed_probe"):
            probe_value = {"outcome": "previously-probed", "date": entry.get("probe_date"),
                           "summary": entry["observed_probe"], "artifact": "SOURCE_TOOLS_IMPLEMENTATION_REPORT.md"}
        access_url, prereq, finding = REVIEWS.get(name, (entry.get("documentation_url"),
                                                          "", entry.get("conditions", "")))
        result.append({
            "id": source_id,
            "name": name,
            "category": "public_api" if name in EXISTING_API_NAMES else
                        "enterprise_ats" if name in ENTERPRISE else "platform",
            "preferred_tool": preferred,
            "runtime_version": runtime_version,
            "runtime_installed": bool(tool and tool not in {"existing_public_api", "unassigned"}),
            "wrapper_tested": bool(tool and tool not in {"existing_public_api", "unassigned"}),
            "state": state,
            "official_url": url,
            "official_url_kind": url_kind,
            "documentation_or_access_url": access_url,
            "country_or_programme_scope": scope,
            "source_access": entry.get("access", "unverified"),
            "access_finding": finding,
            "outstanding_input": prereq or entry.get("required_prerequisite") or reason,
            "pagination_and_detail_limit": entry.get("pagination", "Not verified; one page cannot prove catalogue completeness."),
            "profile_id": profile_id,
            "last_technical_probe": probe_value,
            "prior_existing_probe": entry.get("observed_probe"),
            "conditions": entry.get("conditions", ""),
            "prior_implementation_state": entry.get("implementation"),
        })

    if not any(row["name"] == "Shine" for row in result):
        probe = probes.get("shine")
        result.append({
            "id": "shine", "name": "Shine", "category": "platform", "preferred_tool": "shine",
            "runtime_version": _tool_version("shine"), "runtime_installed": True, "wrapper_tested": True,
            "state": "partial" if probe and probe.get("sample_shape", {}).get("job_count", 0) else "planned",
            "official_url": PLATFORM_URLS["Shine"], "official_url_kind": "official_source_entry",
            "documentation_or_access_url": PLATFORM_URLS["Shine"],
            "country_or_programme_scope": OMKAR_SITES["shine"].country_scope,
            "source_access": "bounded_public_technical_probe; further reuse terms review remains for Part 2",
            "access_finding": OMKAR_SITES["shine"].limitation,
            "outstanding_input": "Review source terms/reuse boundaries for the intended use and confirm the local endpoint/schema remains stable.",
            "pagination_and_detail_limit": "One local search request observed; upstream `has_more`/next-page behavior was observed but not exhausted.",
            "profile_id": None, "last_technical_probe": _probe_detail(probe), "prior_existing_probe": None,
            "conditions": OMKAR_SITES["shine"].limitation,
        })
    for source_id, (name, url, scope) in EXTRA_TARGETS.items():
        probe = probes.get(source_id)
        result.append({
            "id": source_id, "name": name, "category": "campus_platform", "preferred_tool": "crawl4ai",
            "runtime_version": _tool_version("crawl4ai"), "runtime_installed": True, "wrapper_tested": True,
            "state": "login-required", "official_url": url, "official_url_kind": "public_product_entry",
            "documentation_or_access_url": url, "country_or_programme_scope": scope,
            "source_access": "login-required", "access_finding": "No public job-search route is established.",
            "outstanding_input": "A source-supported public jobs route or authorized export; the probe did not use a session.",
            "pagination_and_detail_limit": "No request was made; profile is gated before network access.",
            "profile_id": source_id, "last_technical_probe": _probe_detail(probe),
            "prior_existing_probe": None, "conditions": "Candidate login not used.",
            "prior_implementation_state": "not_connected",
        })
    return result


def build_employers(probes: dict[str, dict]) -> list[dict]:
    if not REPORT.is_file():
        raise FileNotFoundError(REPORT)
    directory = company_directory()
    by_company = {item["company"].casefold(): item for item in directory}
    aliases = {"razorpay": "razorpay software private limited", "microsoft": "microsoft ai"}
    statuses: dict[str, str] = {}
    for line in REPORT.read_text(encoding="utf-8").splitlines():
        match = URL_CELL.match(line.strip())
        if match:
            statuses[match.group(1).strip()] = match.group(3).strip()
    rows = []
    for name in EMPLOYER_URLS:
        raw_url = EMPLOYER_URLS[name]
        lookup = aliases.get(name.casefold(), name.casefold())
        mapping = by_company.get(lookup)
        probe_id = PROFILE_IDS.get(name, "greenhouse-stripe" if name == "Stripe" else None)
        probe = probes.get(probe_id or "")
        observed_count = (probe.get("sample_shape") or {}).get("job_count", 0) if probe else 0
        if probe and probe.get("outcome") == "login_required":
            state = "login-required"
            outstanding = (probe.get("failure") or {}).get("safe_message", "A public job-search route is needed.")
        elif probe and probe.get("outcome") in {"blocked", "timeout", "rate_limited"}:
            state = "blocked"
            outstanding = (probe.get("failure") or {}).get("safe_message", "Retry only after resolving this exact public access/technical blocker.")
        elif probe and observed_count:
            state = "partial"
            outstanding = "Returned a bounded one-page sample; verify employer-relevant search route, regional/programme split, pagination and ATS mapping before connection."
        elif mapping:
            state = "mapped"
            outstanding = "Mapping evidence is a reviewed board URL; no Part 1 live employer fetch is claimed. Connect explicitly in Part 2 after review."
        else:
            state = "planned"
            outstanding = "Verify current official ATS/feed and exact search route; do not guess a tenant slug."
        if name in {"TCS", "Deloitte"}:
            scope = "India careers entry; separate graduate/experienced and legal-entity coverage is required; exact scope not verified."
        elif name == "Accenture":
            scope = "Official India careers entry; graduate and experienced search routes remain unverified."
        elif name == "Microsoft":
            scope = "Candidate URL is the global careers site; existing Greenhouse mapping covers Microsoft AI only."
        else:
            scope = "Employer-dependent; country, legal entity, and graduate/experienced programme coverage not established."
        rows.append({
            "name": name,
            "official_careers_url": raw_url,
            "state": state,
            "preferred_tool": "ats_scrapers" if mapping or probe_id == "greenhouse-stripe" else "crawl4ai_reviewed_profile",
            "runtime_version": _tool_version("ats_scrapers" if mapping or probe_id == "greenhouse-stripe" else "crawl4ai"),
            "country_or_programme_scope": scope,
            "mapping": ({"provider": mapping["provider"], "board": mapping["board"],
                         "mapping_evidence": mapping["mapping_evidence"],
                         "verified_for_setup": mapping["verified_for_setup"],
                         "mapping_scope": mapping["mapping_scope"]} if mapping else None),
            "technical_probe": _probe_detail(probe),
            "source_report_mapping_state": statuses.get(name, "candidate retained"),
            "outstanding_input": outstanding,
        })
    return rows


def main() -> int:
    probes, artifacts = _load_probe_index()
    sources = build_sources(probes)
    employers = build_employers(probes)
    allowed_states = {"planned", "downloaded", "installed", "wrapper-tested", "mapped",
                      "live-verified", "partial", "blocked", "login-required", "unsupported",
                      "excluded-paid", "not-a-job-catalogue"}
    assert len(source_register()) == 45, f"original source count changed: {len(source_register())}"
    assert len(sources) == 47, f"expected original 45 sources plus Shine and the Part 1 Superset target; found {len(sources)}"
    assert len(employers) == 51, f"expected all employer candidates; found {len(employers)}"
    assert len({row["id"] for row in sources}) == len(sources), "duplicate source ids found"
    assert len({row["name"] for row in employers}) == len(employers), "duplicate employer candidates found"
    assert all(row["state"] in allowed_states for row in sources + employers), "invalid coverage state found"
    payload = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "part": "Open Source Discovery Part 1",
        "scope_note": "Source installation, wrapper and bounded technical coverage. This is not an activation list or a claim of exhaustive job catalogue coverage.",
        "source_count": len(sources),
        "source_count_before_part1": 45,
        "shine_added": True,
        "additional_named_part1_target": "Superset",
        "employer_candidate_count": len(employers),
        "probe_artifacts": artifacts,
        "sources": sources,
        "employers": employers,
    }
    destination = ROOT / "OSS_SOURCE_COVERAGE.json"
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {"output": str(destination), "sources": len(sources), "employers": len(employers),
               "states": {state: sum(row["state"] == state for row in sources) for state in sorted({r["state"] for r in sources})},
               "employer_states": {state: sum(row["state"] == state for row in employers) for state in sorted({r["state"] for r in employers})}}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
