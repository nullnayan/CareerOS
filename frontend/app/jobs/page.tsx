"use client";
import Link from "next/link";
import { FormEvent, useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { Button, Section } from "../components/ui";
import { personal } from "../lib/personal";
import { Catalog, Feed, Job, SearchPreferences, Source } from "../lib/jobs";

import ConnectionsPanel from "./connections-panel";
import OSSConnectionsPanel from "./oss-connections-panel";

const input = "w-full min-w-0 rounded border border-rule bg-surface p-2.5 text-sm text-ink";
const initial: SearchPreferences = { target_roles: ["Software Engineer", "Backend Developer"], locations: ["India"], work_modes: ["remote", "hybrid", "onsite"], employment_types: ["full_time"], graduation_year: null, education_status: "unspecified", institution: "", earliest_joining_date: null, max_required_experience: 0, minimum_salary_annual_inr: 550000, excluded_companies: [], country_code: "in", max_posting_age_days: 60 };
const sourceTime = (value: string | number) => typeof value === "number" ? new Date(value < 100000000000 ? value * 1000 : value).toLocaleString() : time(value);
const time = (value: string | null) => value ? new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : value + "Z").toLocaleString() : "Not yet";

function StatusChecks({ job }: { job: Job }) {
  const checks = Object.values(job.facts.source_status_checks || {}) as { status: string; checked_at: string }[];
  if (!checks.length) return null;
  const latest = [...checks].sort((a, b) => b.checked_at.localeCompare(a.checked_at))[0];
  return <p className={`mt-2 text-xs ${latest.status === "unknown" ? "text-warn" : "text-ink-tertiary"}`}>Source availability check: {latest.status === "unknown" ? "Unconfirmed — verify the original listing" : latest.status} · {time(latest.checked_at)}</p>;
}

function SalaryUncertainty({ job }: { job: Job }) {
  if (job.facts.annual_salary_min_inr) return null;
  const currency = job.facts.salary_currency;
  return <p className="mt-2 text-sm text-ink-secondary">{currency ? `Salary disclosed in ${currency}; minimum annual INR pay is not verified. LPA filter not applied.` : "Salary not disclosed — LPA filter not applied."}</p>;
}

export default function JobsPage() {
  const router = useRouter();
  const [tab, setTab] = useState("feed");
  const [prefs, setPrefs] = useState<SearchPreferences>(initial);
  const [confirmed, setConfirmed] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [feed, setFeed] = useState<Feed | null>(null);
  const [busy, setBusy] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [q, setQ] = useState("");
  const [eligibility, setEligibility] = useState("suitable");
  const [state, setState] = useState("active");
  const [sourceFilter, setSourceFilter] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("best");
  const [hasSearched, setHasSearched] = useState(false);
  const [searchId, setSearchId] = useState("");
  const [searching, setSearching] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);
  const [workMode, setWorkMode] = useState("");
  const [employment, setEmployment] = useState("");
  const [experience, setExperience] = useState(0);
  const [includeUnknownExperience, setIncludeUnknownExperience] = useState(true);
  const [salaryFloor, setSalaryFloor] = useState("5.5");
  const [includeUnverifiedSalary, setIncludeUnverifiedSalary] = useState(true);
  const [postedWithin, setPostedWithin] = useState(0);
  const feedRequest = useRef(0);
  const [detail, setDetail] = useState<Job | null>(null);
  const [importing, setImporting] = useState(false);
  const [history, setHistory] = useState<{ id: string; status: string; started_at: string; summary: any }[]>([]);

  async function loadFeed() {
    if (!hasSearched) return;
    const request = ++feedRequest.current; setLoading(true);
    try { const result = await personal<Feed>("/jobs?" + new URLSearchParams({ q, eligibility, state, source_id: sourceFilter, page: String(page), sort, work_mode: workMode, employment_type: employment, max_experience: String(experience), include_unknown_experience: String(includeUnknownExperience), salary_floor: String(Math.min(100000000, Math.max(0, Math.round((Number(salaryFloor) || 0) * 100000)))), include_unverified_salary: String(includeUnverifiedSalary), posted_within: String(postedWithin) })); if (request === feedRequest.current) setFeed(result); }
    catch (e: any) { if (request === feedRequest.current) setError(e.message); } finally { if (request === feedRequest.current) setLoading(false); }
  }
  async function loadSources() {
    const [s, h] = await Promise.all([personal<Source[]>("/jobs/sources"), personal<typeof history>("/jobs/refreshes")]);
    setSources(s.filter(source => !(source as Source & { archived?: boolean }).archived)); setHistory(h);
  }
  useEffect(() => {
    Promise.all([personal<{ preferences: SearchPreferences; confirmed: boolean }>("/jobs/preferences"), personal<Catalog>("/jobs/catalog")])
      .then(([p, c]) => { setPrefs(p.preferences); setPostedWithin(p.preferences.max_posting_age_days || 0); setExperience(p.preferences.max_required_experience); setConfirmed(p.confirmed); setCatalog(c); }).catch(e => setError(e.message));
    loadSources().catch(e => setError(e.message));
  }, []);
  useEffect(() => { const timer = setTimeout(loadFeed, 250); return () => clearTimeout(timer); }, [hasSearched, q, eligibility, state, sourceFilter, page, sort, workMode, employment, experience, includeUnknownExperience, salaryFloor, includeUnverifiedSalary, postedWithin, refreshTick]);
  useEffect(() => { setPage(1); }, [q, eligibility, state, sourceFilter, sort, workMode, employment, experience, includeUnknownExperience, salaryFloor, includeUnverifiedSalary, postedWithin]);
  useEffect(() => {
    if (!searchId) return;
    let cancelled = false;
    async function poll() {
      try {
        const status = await personal<{ status: string; pending: number; completed_batches: number; errors: string[]; worker_running: boolean; coverage: { checked_sources: number; enabled_sources: number; remaining_sources: string[]; more_pages: boolean } }>(`/jobs/search/${searchId}`);
        if (cancelled) return;
        setRefreshTick(t => t + 1); await loadSources();
        if (status.status !== "running") { setSearching(false); setSearchId(""); setNotice(`Search ${status.status}: ${status.coverage.checked_sources}/${status.coverage.enabled_sources} sources checked.${status.status === "incomplete" ? " Some scan batches were not continued. Reload the worker and click Search jobs again." : status.coverage.remaining_sources.length ? " Some sources were deferred or unavailable; see Sources." : ""} ${status.errors.join(" ")}`); }
        else setNotice(status.worker_running ? `${status.coverage.checked_sources}/${status.coverage.enabled_sources} sources checked. ${status.pending} batches queued or running; provider cooldowns are respected.` : "Search is queued. The local worker is not running; open Automation for worker status and start it in your own terminal.");
      } catch (e: any) { if (!cancelled) { setError(e.message); setSearching(false); setSearchId(""); } }
    }
    poll(); const timer = setInterval(poll, 3000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [searchId]);
  function field<K extends keyof SearchPreferences>(name: K, value: SearchPreferences[K]) { setPrefs(p => ({ ...p, [name]: value })); if (name === "max_required_experience") setExperience(Number(value)); if (name === "max_posting_age_days") setPostedWithin(Number(value) || 0); }
  function toggle(name: "work_modes" | "employment_types", value: string) {
    field(name, prefs[name].includes(value) ? prefs[name].filter(item => item !== value) : [...prefs[name], value]);
  }
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy("Saving preferences"); setError(""); setNotice("");
    try { await personal("/jobs/preferences", "PUT", prefs); setConfirmed(true); setNotice("Preferences saved. Existing matches were reassessed."); await loadFeed(); }
    catch (e: any) { setError(e.message); } finally { setBusy(""); }
  }
  async function addSource(provider: string, board: string, company: string) {
    setBusy("Adding source"); setError("");
    try { await personal("/jobs/sources", "POST", { provider, board, company }); await loadSources(); }
    catch (e: any) { setError(e.message); } finally { setBusy(""); }
  }
  async function refresh() {
    setBusy("Starting job search"); setError(""); setNotice("");
    try {
      const searchPreferences = { ...prefs, max_required_experience: experience, max_posting_age_days: postedWithin || null };
      await personal("/jobs/preferences", "PUT", searchPreferences);
      setPrefs(searchPreferences);
      const result = await personal<{ search_id: string; status: string }>("/jobs/search", "POST");
      setHasSearched(true); setSearching(true); setSearchId(result.search_id); setPage(1); setTab("feed");
      setNotice("Search queued. Your local worker checks connected sources; no applications or resume PDFs are submitted by this search.");
    } catch (e: any) { setError(e.message); } finally { setBusy(""); }
  }
  async function changeState(job: Job, next: string) {
    setBusy("Updating job"); setError("");
    try { const updated = await personal<Job>(`/jobs/${job.id}/state`, "PATCH", { state: next }); if (detail?.id === job.id) setDetail({ ...detail, ...updated }); await loadFeed(); }
    catch (e: any) { setError(e.message); } finally { setBusy(""); }
  }
  async function openDetail(id: string) {
    setBusy("Loading description"); setError("");
    try { setDetail(await personal<Job>(`/jobs/${id}`)); } catch (e: any) { setError(e.message); } finally { setBusy(""); }
  }
  async function tailor(job: Job) {
    setBusy("Preparing skill review"); setError("");
    try { const result = await personal<{ url: string }>(`/jobs/${job.id}/tailor`, "POST"); router.push(result.url); }
    catch (e: any) { setError(e.message); } finally { setBusy(""); }
  }
  async function queueResume(job: Job) {
    setBusy("Queuing resume preparation"); setError(""); setNotice("");
    try { await personal(`/automation/prepare/${job.id}`, "POST"); setNotice("Resume preparation queued. Check Automation for progress; new skills still require your confirmation."); }
    catch (e: any) { setError(e.message); } finally { setBusy(""); }
  }
  async function track(job: Job) {
    setBusy("Adding application"); setError("");
    try { const result = await personal<{ id: string }>("/applications", "POST", { job_id: job.id }); router.push(`/applications?application=${result.id}`); }
    catch (e: any) { setError(e.message); } finally { setBusy(""); }
  }
  async function importJob(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget); setBusy("Saving supplied job"); setError("");
    try { const result = await personal<Job>("/jobs/import", "POST", { title: form.get("title"), company: form.get("company"), location: form.get("location"), apply_url: form.get("apply_url"), description: form.get("description"), description_complete: form.get("complete") === "on" }); setImporting(false); setDetail(result); await loadSources(); await loadFeed(); }
    catch (e: any) { setError(e.message); } finally { setBusy(""); }
  }

  return <div className="space-y-7">
    {searching && <Button variant="secondary" disabled={!!busy} onClick={async () => { setBusy("Pausing search"); try { await personal("/jobs/pause", "POST"); setSearching(false); setSearchId(""); setNotice("Search paused. Running collectors were signalled to stop; saved jobs were retained."); } catch (e: any) { setError(e.message); } finally { setBusy(""); } }}>Pause search</Button>}
    <div className="flex flex-wrap items-end justify-between gap-4"><div><h1 className="font-serif text-4xl">Find your next role</h1><p className="mt-2 max-w-2xl text-ink-secondary">Jobs from connected boards, filtered by your requirements and sorted by work arrangement, salary or date.</p></div><Button onClick={refresh} disabled={!!busy || searching || !confirmed || !sources.some(s => s.enabled && !["adzuna", "manual"].includes(s.provider))}>Search jobs</Button></div>
    <nav aria-label="Job tools" className="flex flex-wrap gap-5 text-sm"><Link href="/automation" className="text-accent underline">Automation</Link><Link href="/applications" className="text-accent underline">Applications</Link><Link href="/autofill" className="text-accent underline">Browser autofill</Link></nav>
    <div className="flex gap-5 border-b border-rule" role="tablist" aria-label="Job workspace">{[["feed", "Discover"], ["preferences", "Preferences"], ["sources", "Sources"]].map(([value, label]) => <button key={value} role="tab" aria-selected={tab === value} onClick={() => { setTab(value); setDetail(null); }} className={`border-b-2 pb-3 text-sm ${tab === value ? "border-accent text-accent" : "border-transparent text-ink-secondary"}`}>{label}</button>)}</div>
    {error && <p role="alert" className="whitespace-pre-wrap rounded border border-bad/30 p-3 text-bad">{error}</p>}
    {notice && <p role="status" className="whitespace-pre-wrap border-l-2 border-accent pl-3 text-sm">{notice}</p>}
    {busy && <p role="status" className="text-sm text-accent">{busy}…</p>}{busy === "Refreshing company boards" && history[0]?.status === "running" && <p className="text-xs text-ink-tertiary">{history[0].summary?.sources?.length || 0} source checks completed in this run. Remaining work follows polling and execution budgets.</p>}

    {tab === "preferences" && <form onSubmit={save} className="space-y-7"><Section title="Your fresher search" description="Save these choices before running a search. Unknown requirements will remain visible for review.">
      <div className="grid gap-5 sm:grid-cols-2">
        <label className="space-y-1 text-sm">Target roles (comma separated)<input className={input} value={prefs.target_roles.join(", ")} onChange={e => field("target_roles", e.target.value.split(",").map(value => value.trimStart()))} required /></label>
        <label className="space-y-1 text-sm">Locations (comma separated)<input className={input} value={prefs.locations.join(", ")} onChange={e => field("locations", e.target.value.split(",").map(value => value.trimStart()))} placeholder="India, Bengaluru, Pune" /></label>
        <label className="space-y-1 text-sm">Graduation year<input type="number" min={2000} max={2040} className={input} value={prefs.graduation_year ?? ""} onChange={e => field("graduation_year", e.target.value ? Number(e.target.value) : null)} /></label>
        <label className="space-y-1 text-sm">Education status<select className={input} value={prefs.education_status} onChange={e => field("education_status", e.target.value)}><option value="unspecified">Not confirmed</option><option value="student">Currently studying</option><option value="graduate">Graduated</option></select></label>
        <label className="space-y-1 text-sm">Institution<input className={input} value={prefs.institution} onChange={e => field("institution", e.target.value)} placeholder="Used to check campus-specific openings" /></label>
        <label className="space-y-1 text-sm">Earliest joining date<input type="date" className={input} value={prefs.earliest_joining_date || ""} onChange={e => field("earliest_joining_date", e.target.value || null)} /></label>
        <label className="space-y-1 text-sm">Maximum required experience (years)<input type="number" min={0} max={10} step={0.5} className={input} value={prefs.max_required_experience} onChange={e => field("max_required_experience", Number(e.target.value))} /></label>
        <label className="space-y-1 text-sm">Minimum annual salary, INR<input type="number" min={0} className={input} value={prefs.minimum_salary_annual_inr ?? ""} onChange={e => field("minimum_salary_annual_inr", e.target.value ? Number(e.target.value) : null)} /></label>
        <label className="space-y-1 text-sm">Degree<input className={input} value={prefs.degree || ""} maxLength={150} onChange={e => field("degree", e.target.value)} /></label><label className="space-y-1 text-sm">Course / specialization<input className={input} value={prefs.course || ""} maxLength={150} onChange={e => field("course", e.target.value)} /></label><label className="space-y-1 text-sm">Exclude companies (comma separated)<input className={input} value={prefs.excluded_companies.join(", ")} onChange={e => field("excluded_companies", e.target.value.split(",").map(value => value.trimStart()))} /></label>
        <label className="space-y-1 text-sm">Maximum posting age, days<input type="number" min={1} max={365} className={input} value={prefs.max_posting_age_days ?? ""} onChange={e => field("max_posting_age_days", e.target.value ? Number(e.target.value) : null)} /></label>
      </div>
      <fieldset><legend className="mb-2 text-sm">Work arrangements</legend><div className="flex flex-wrap gap-5">{["remote", "hybrid", "onsite"].map(value => <label key={value} className="flex items-center gap-2 text-sm capitalize"><input type="checkbox" checked={prefs.work_modes.includes(value)} onChange={() => toggle("work_modes", value)} />{value}</label>)}</div></fieldset>
      <fieldset><legend className="mb-2 text-sm">Employment types</legend><div className="flex flex-wrap gap-5">{[["full_time", "Full time"], ["internship", "Internship"], ["contract", "Contract"], ["part_time", "Part time"]].map(([value, label]) => <label key={value} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={prefs.employment_types.includes(value)} onChange={() => toggle("employment_types", value)} />{label}</label>)}</div></fieldset>
      <Button type="submit" disabled={!!busy}>Save job preferences</Button>
    </Section></form>}

    {tab === "sources" && (catalog?.engine === "legacy" ? <div className="space-y-8"><ConnectionsPanel onChange={loadSources} /><Section title="Connected sources" description="A source failure preserves existing listings. Refresh checks live listings; it does not submit applications.">
      {!sources.length && <p className="text-ink-secondary">No sources connected yet. Add a company board below.</p>}
      {sources.map(source => <div key={source.id} className="space-y-1 border-b border-rule py-3"><div className="flex items-center justify-between gap-3"><div className="min-w-0"><strong>{source.company}</strong><span className="ml-2 break-all text-xs text-ink-tertiary">{source.provider} · {source.board}</span></div>{source.provider !== "manual" && <Button variant="secondary" disabled={!!busy} onClick={async () => { try { await personal(`/jobs/sources/${source.id}`, "PATCH", { enabled: !source.enabled }); await loadSources(); } catch (e: any) { setError(e.message); } }}>{source.enabled ? "Disable" : "Enable"}</Button>}</div><p className="text-xs text-ink-tertiary">{source.health || "never checked"} · Last success: {time(source.last_success_at)} · {source.last_count || 0} listings · Next allowed check: {time(source.retry_at || null)}</p>{source.last_scan && <p className="text-xs text-ink-tertiary">Scope: {source.last_scan.scope} · Pages: {source.last_scan.pages} · {source.last_scan.complete_snapshot ? "Complete board" : "Partial / window scan"} · {source.last_scan.truncation_reason || ""}</p>}{source.last_error && <p className="text-sm text-bad">{source.last_error}</p>}</div>)}
    </Section>
    <Section title="Company board directory" description="Documented public board interfaces. Jobs may still require a different graduation batch or campus."><div className="grid gap-3 sm:grid-cols-2">{catalog?.company_boards.map(item => <div key={item.provider + item.board} className="flex items-center justify-between gap-3 rounded border border-rule p-4"><div><a href={item.url} target="_blank" rel="noreferrer" className="text-accent underline">{item.company}</a><p className="mt-1 text-xs text-ink-tertiary">{item.provider}</p></div><Button variant="secondary" disabled={!!busy || sources.some(s => s.provider === item.provider && s.board === item.board)} onClick={() => addSource(item.provider, item.board, item.company)}>Add source</Button></div>)}</div></Section>
    <Section title="Add another company board"><form className="grid items-end gap-3 sm:grid-cols-4" onSubmit={e => { e.preventDefault(); const form = new FormData(e.currentTarget); addSource(String(form.get("provider")), String(form.get("board")), String(form.get("company"))); }}><label className="space-y-1 text-sm">Provider<select aria-label="Provider" name="provider" className={input}><option value="auto">Detect from board URL</option><option value="greenhouse">Greenhouse</option><option value="lever">Lever</option><option value="ashby">Ashby</option><option value="smartrecruiters">SmartRecruiters</option><option value="workable">Workable</option></select></label><label className="space-y-1 text-sm">Company<input name="company" required className={input} maxLength={150} /></label><label className="space-y-1 text-sm">Board URL or identifier<input name="board" required className={input} maxLength={300} /></label><Button type="submit" disabled={!!busy}>Connect board</Button></form></Section>
    <Section title="Free public feeds" description="Rolling windows are incomplete coverage. Attribution and source links are retained. Disappearance from a feed does not mean closure; explicit status checks can confirm it."><div className="flex flex-wrap gap-3">{["remotive", "jobicy", "himalayas"].map(provider => <Button key={provider} variant="secondary" disabled={!!busy || sources.some(s => s.provider === provider)} onClick={() => addSource(provider, "public", provider === "remotive" ? "Remotive" : provider === "jobicy" ? "Jobicy" : "Himalayas")}>Add {provider === "remotive" ? "Remotive (24h delay)" : provider === "jobicy" ? "Jobicy (7-day window, 3h delay)" : "Himalayas (daily feed)"}</Button>)}</div><p className="text-xs text-ink-tertiary">Adzuna is excluded from free discovery; its historical records and credentials are retained.</p></Section>
    <Section title="Source access register" description="Inventory is separate from connected sources. Unverified and permission-required entries do not run discovery."><div className="grid gap-3 sm:grid-cols-2">{catalog?.source_register.map(item => <div key={item.id} className="min-w-0 rounded border border-rule p-3"><strong>{item.name}</strong><p className="text-xs text-ink-tertiary">{item.access.replaceAll("_", " ")} · {item.implementation} · {item.cost.replaceAll("_", " ")}</p><p className="mt-1 text-sm text-ink-secondary">{item.conditions}</p><p className="mt-1 text-xs">Documentation check: {item.checked_at || "Not verified"} · Poll floor: {item.polling_floor_seconds ? `${item.polling_floor_seconds / 3600}h` : "Not enabled"}</p>{item.observed_probe && <p className="text-xs text-ink-secondary">Probe {item.probe_date}: {item.observed_probe}</p>}{item.documentation_url && <a className="text-xs text-accent underline" href={item.documentation_url} target="_blank" rel="noreferrer">Access documentation ↗</a>}</div>)}</div><details><summary className="cursor-pointer text-sm">Employer directory candidates (mappings need verification)</summary><p className="text-sm text-ink-secondary">{catalog?.employer_candidates.join(", ")}</p></details></Section>
    <Section title="Other job boards" description="These open the original sites. CareerOS does not currently import or automate their listings."><div className="flex flex-wrap gap-5">{catalog?.external_only.map(item => <a key={item.name} href={item.url} target="_blank" rel="noreferrer" className="text-sm text-accent underline">{item.name} ↗</a>)}</div></Section>
    </div> : <OSSConnectionsPanel onChange={loadSources} />)}

    {tab === "feed" && <div className="space-y-6">
      {!confirmed && <div className="border-l-2 border-accent pl-4"><p>First, confirm your target roles and fresher eligibility.</p><button onClick={() => setTab("preferences")} className="mt-2 text-accent underline">Set job preferences →</button></div>}
      {confirmed && !sources.some(s => s.enabled) && <p>Add a source under <button onClick={() => setTab("sources")} className="text-accent underline">Sources</button>, then click Search jobs.</p>}
      {feed && !feed.master_active && <p className="text-sm text-ink-secondary"><Link href="/master" className="text-accent underline">Activate your reviewed master</Link> to include resume evidence in matching and prepare job-specific skill reviews.</p>}
      <div className="grid gap-3 sm:grid-cols-4"><input aria-label="Search jobs" placeholder="Filter results: role, company, location" value={q} onChange={e => setQ(e.target.value)} className={input} /><select aria-label="Eligibility filter" value={eligibility} onChange={e => setEligibility(e.target.value)} className={input}><option value="suitable">Potential matches + review</option><option value="eligible">Passes stated checks</option><option value="review">Needs eligibility review</option><option value="ineligible">Outside preferences</option><option value="all">All eligibility</option></select><select aria-label="Saved state" value={state} onChange={e => setState(e.target.value)} className={input}><option value="active">Active feed</option><option value="saved">Saved</option><option value="dismissed">Dismissed</option><option value="all">All states</option></select><select aria-label="Source filter" value={sourceFilter} onChange={e => setSourceFilter(e.target.value)} className={input}><option value="">All sources</option>{sources.map(s => <option key={s.id} value={s.id}>{s.company}</option>)}</select></div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="text-sm">Sort jobs<select aria-label="Job sort" value={sort} onChange={e => setSort(e.target.value)} className={input}><option value="best">WFH first, highest package, newest</option><option value="wfh_first">WFH first</option><option value="onsite_first">On-site first</option><option value="salary_desc">Salary: highest first</option><option value="salary_asc">Salary: lowest first</option><option value="newest">Newest published / first seen</option></select></label>
        <label className="text-sm">Work arrangement<select aria-label="Work arrangement filter" className={input} value={workMode} onChange={e => setWorkMode(e.target.value)}><option value="">All arrangements</option><option value="remote">WFH / remote</option><option value="hybrid">Hybrid</option><option value="onsite">On-site</option></select></label>
        <label className="text-sm">Employment type<select aria-label="Employment type filter" className={input} value={employment} onChange={e => setEmployment(e.target.value)}><option value="">All preferred types</option><option value="full_time">Full time</option><option value="internship">Internship</option><option value="contract">Contract</option><option value="part_time">Part time</option></select></label>
        <label className="text-sm">Annual salary above, lakh INR<input aria-label="Salary above LPA" type="number" min={0} max={1000} step={0.1} placeholder="Any" value={salaryFloor} onChange={e => setSalaryFloor(e.target.value)} className={input} /></label>
        <label className="text-sm">Your experience<select aria-label="Experience filter" value={experience} onChange={e => setExperience(Number(e.target.value))} className={input}>{Array.from({ length: 21 }, (_, index) => index / 2).map(years => <option key={years} value={years}>{years === 0 ? "Fresher — 0 years" : `${years} year${years === 1 ? "" : "s"}`}</option>)}</select></label>
        <label className="text-sm">Published within<select aria-label="Posting age filter" value={postedWithin} onChange={e => setPostedWithin(Number(e.target.value))} className={input}><option value={0}>Any known or unknown date</option><option value={1}>Last 1 day</option><option value={3}>Last 3 days</option><option value={7}>7 days</option><option value={14}>14 days</option><option value={30}>30 days</option><option value={60}>60 days</option><option value={90}>90 days</option></select></label>
      </div><div className="flex flex-wrap items-center gap-4"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={includeUnverifiedSalary} onChange={e => setIncludeUnverifiedSalary(e.target.checked)} />Include jobs with undisclosed or unverified salary</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={includeUnknownExperience} onChange={e => setIncludeUnknownExperience(e.target.checked)} />Include jobs with experience not stated</label><Button variant="ghost" onClick={() => { setExperience(0); setIncludeUnknownExperience(true); setSalaryFloor("5.5"); setIncludeUnverifiedSalary(true); setWorkMode(""); setEmployment(""); setPostedWithin(0); setSourceFilter(""); setEligibility("suitable"); setState("active"); setSort("best"); setQ(""); }}>Reset filters</Button></div><p className="text-xs text-ink-tertiary">Experience includes jobs whose stated minimum fits your selected years. Unknown experience stays clearly marked unless excluded. Date and experience selections are applied when you click Search jobs; changing filters alone does not start collection. Enter 0 to remove the salary filter.</p><div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-ink-tertiary">{loading ? "Updating matches…" : feed ? `${feed.total} matching · ${feed.stored} stored` : "Click Search jobs when you are ready."}</p><Button variant="secondary" onClick={() => setImporting(p => !p)}>Add a job description</Button></div>
      {feed?.diagnostics && <p role="status" className="text-sm text-ink-secondary">{feed.stored} fetched · {feed.diagnostics.eligible_matches} match eligibility/filters · {feed.diagnostics.salary_unverified_matches} have unverified salary · {feed.diagnostics.salary_excluded} excluded by salary controls.</p>}
      {importing && <Section title="Job you found elsewhere" description="Paste content you are permitted to use. CareerOS saves this text; it does not crawl the URL."><form onSubmit={importJob} className="space-y-3"><div className="grid gap-3 sm:grid-cols-2">{[["title", "Job title"], ["company", "Company"], ["location", "Location"], ["apply_url", "Original application URL"]].map(([name, label]) => <label key={name} className="space-y-1 text-sm">{label}<input name={name} defaultValue={detail ? String(detail[name as keyof Job] || "") : ""} required={name !== "location"} className={input} type={name === "apply_url" ? "url" : "text"} /></label>)}</div><label className="block space-y-1 text-sm">Job description<textarea name="description" defaultValue={detail?.description || ""} required minLength={50} maxLength={100000} rows={8} className={input} /></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" name="complete" defaultChecked />This is the full job description.</label><Button disabled={!!busy} type="submit">Save supplied job</Button></form></Section>}
      {detail && <Section title={detail.title} description={`${detail.company} · ${detail.location || "Location not supplied"}`} action={<button onClick={() => setDetail(null)} className="text-sm underline">Close details</button>}><p className="text-sm text-ink-tertiary">{detail.description_complete ? "Full description" : "Search excerpt — full description needed for tailoring"}</p><SalaryUncertainty job={detail} /><StatusChecks job={detail} /><div className="max-h-[600px] overflow-auto whitespace-pre-wrap border-y border-rule py-4 text-sm leading-relaxed">{detail.description}</div><div className="flex flex-wrap gap-4">{!detail.description_complete && <Button variant="secondary" onClick={() => setImporting(true)}>Supply full job description</Button>}<a href={detail.apply_url} target="_blank" rel="noreferrer" className="text-accent underline">Open original application ↗</a><Button disabled={!!busy || !detail.description_complete || !feed?.master_active || detail.status !== "open"} onClick={() => tailor(detail)}>Review resume skills</Button><Button variant="secondary" disabled={!!busy || !detail.description_complete || !feed?.master_active || detail.status !== "open"} onClick={() => queueResume(detail)}>Queue resume PDF</Button><Button variant="secondary" disabled={!!busy} onClick={() => track(detail)}>Track application</Button></div></Section>}
      <div className="space-y-4">{feed?.items.map(job => <article key={job.id} className="rounded border border-rule bg-surface p-5"><div className="flex items-start justify-between gap-4"><div><h2 className="text-xl">{job.title}</h2><p className="mt-1 text-sm text-ink-secondary">{job.company} · {job.location || "Location not supplied"}</p></div></div><p className={`mt-3 text-sm ${job.assessment.eligibility === "ineligible" ? "text-bad" : job.assessment.eligibility === "review" ? "text-warn" : "text-good"}`}>{job.assessment.eligibility === "eligible" ? "Passes stated checks" : job.assessment.eligibility === "review" ? "Needs eligibility review" : "Outside stated requirements / preferences"}{job.status === "closed" ? " · Closed" : ""}{job.state === "saved" ? " · Saved" : ""}</p><ul className="mt-3 space-y-1 text-sm text-ink-secondary">{job.assessment.reasons.slice(0, 3).map(reason => <li key={reason}>{reason}</li>)}</ul>{!!job.assessment.blocked_reasons.length && <p className="mt-3 text-sm text-bad">{job.assessment.blocked_reasons.join(" ")}</p>}{!!job.assessment.unknowns.length && <p className="mt-3 text-sm text-warn">{job.assessment.unknowns.slice(0, 2).join(" ")}</p>}<p className="mt-3 text-xs text-ink-tertiary">{job.published_at ? `Published: ${time(job.published_at)} · ` : "Publication date not supplied · "}First seen: {time(job.first_seen_at)} · Last verified: {time(job.last_seen_at)}{Date.now() - Date.parse(job.last_seen_at + "Z") > 86400000 ? " · Verification older than 24h; check original" : ""}{job.facts.source_updated_at ? ` · Updated by source: ${sourceTime(job.facts.source_updated_at)}` : ""} · {job.source_ids.map(id => sources.find(s => s.id === id)?.company).filter(Boolean).join(", ")}{!job.description_complete ? " · Excerpt only" : ""}{job.facts.attribution && <> · Source: <a className="text-accent underline" href={job.facts.source_url} target="_blank" rel="noreferrer">{job.facts.attribution}</a></>}{job.resume_status ? ` · Resume: ${job.resume_status}` : ""}</p>{job.facts.annual_salary_min_inr && <p className="mt-2 text-sm font-medium">₹{(job.facts.annual_salary_min_inr / 100000).toLocaleString("en-IN", { maximumFractionDigits: 2 })}{job.facts.annual_salary_max_inr !== job.facts.annual_salary_min_inr ? `–${(job.facts.annual_salary_max_inr / 100000).toLocaleString("en-IN", { maximumFractionDigits: 2 })}` : ""} lakh / year · {job.assessment.work_mode === "remote" ? "WFH / remote" : job.assessment.work_mode}</p>}<p className="mt-2 text-sm text-ink-secondary">Experience: {job.facts.experience_range || job.facts.experience || (job.assessment.minimum_experience != null ? `${job.assessment.minimum_experience} years minimum` : "Not stated — check the original listing")}</p><SalaryUncertainty job={job} /><StatusChecks job={job} /><div className="mt-4 flex flex-wrap items-center gap-3"><Button variant="secondary" disabled={!!busy} onClick={() => openDetail(job.id)}>View details</Button><Button variant="ghost" disabled={!!busy} onClick={() => track(job)}>Track application</Button><Button variant="ghost" disabled={!!busy} onClick={() => changeState(job, job.state === "saved" ? "new" : "saved")}>{job.state === "saved" ? "Unsave" : "Save"}</Button><Button variant="ghost" disabled={!!busy} onClick={() => changeState(job, job.state === "dismissed" ? "new" : "dismissed")}>{job.state === "dismissed" ? "Restore" : "Dismiss"}</Button><a href={job.apply_url} target="_blank" rel="noreferrer" className="text-sm text-accent underline">Open application ↗</a></div></article>)}</div>
      {feed && !feed.items.length && !loading && <p className="border-y border-rule py-10 text-center text-ink-secondary">No jobs match these filters yet. Check source progress, adjust experience, posting age, salary or work-arrangement filters. Unverified salary is shown when its option is enabled.</p>}
      {feed && <nav aria-label="Job pages" className="flex items-center justify-between gap-3"><Button variant="secondary" disabled={loading || page <= 1} onClick={() => setPage(p => p - 1)}>Previous</Button><span className="text-sm">Page {page} of {Math.max(1, Math.ceil(feed.total / feed.page_size))}</span><Button variant="secondary" disabled={loading || !feed.has_next} onClick={() => setPage(p => p + 1)}>Next</Button></nav>}
      <p className="text-xs text-ink-tertiary">Opening a link does not mark an application as submitted.</p>
      {!!history.length && <details><summary className="cursor-pointer text-sm text-ink-tertiary">Recent refreshes</summary>{history.map(run => <p key={run.id} className="mt-2 text-xs text-ink-secondary">{time(run.started_at)} · {run.status} · {run.summary?.listed || 0} listings</p>)}</details>}
    </div>}
  </div>;
}
