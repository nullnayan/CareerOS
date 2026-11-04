"use client";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { Button, Section } from "../components/ui";
import { artifactUrl, personal, TailoringRun } from "../lib/personal";

type Event = { id: string; event_type: string; from_status: string | null; to_status: string | null; detail: { changed_fields?: string[] }; created_at: string };
type Application = { id: string; job_id: string; title: string; company: string; location: string; apply_url: string; job_status: string; status: string; notes: string; applied_at: string | null; next_action_at: string | null; tailoring_run_id: string | null; resume_pdf_url: string | null; created_at: string; updated_at: string; history?: Event[] };
type Ledger = { items: Application[]; counts: Record<string, number>; total: number };
const statuses = ["planned", "applied", "interview", "offer", "rejected", "withdrawn"];
const input = "w-full min-w-0 rounded border border-rule bg-surface p-2.5 text-sm text-ink";
const display = (value: string | null) => value ? new Date(value + (value.endsWith("Z") ? "" : "Z")).toLocaleString() : "Not set";
const localDate = (value: string | null) => { if (!value) return ""; const date = new Date(value + (value.endsWith("Z") ? "" : "Z")); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16); };

export default function ApplicationsPage() {
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Application | null>(null);
  const [runs, setRuns] = useState<TailoringRun[]>([]);
  const [status, setStatus] = useState("planned");
  const [notes, setNotes] = useState("");
  const [nextAction, setNextAction] = useState("");
  const [appliedAt, setAppliedAt] = useState("");
  const [resume, setResume] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    try { setLedger(await personal<Ledger>("/applications?" + new URLSearchParams({ status: filter, q }))); }
    catch (e: any) { setError(e.message); }
  }
  function open(item: Application) {
    setSelected(item); setStatus(item.status); setNotes(item.notes); setNextAction(localDate(item.next_action_at));
    setAppliedAt(localDate(item.applied_at)); setResume(item.tailoring_run_id || ""); setConfirmed(false);
  }
  async function details(id: string) {
    setError(""); setBusy(true);
    try { open(await personal<Application>(`/applications/${id}`)); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }
  useEffect(() => {
    personal<TailoringRun[]>("/tailor/runs").then(items => setRuns(items.filter(item => item.status === "ready"))).catch(e => setError(e.message));
    const id = new URLSearchParams(window.location.search).get("application");
    if (id) details(id);
  }, []);
  useEffect(() => { const timer = setTimeout(load, 200); return () => clearTimeout(timer); }, [filter, q]);
  async function save(event: FormEvent) {
    event.preventDefault(); if (!selected) return;
    setBusy(true); setError(""); setNotice("");
    const body: Record<string, unknown> = { status, notes, next_action_at: nextAction ? new Date(nextAction).toISOString() : null, confirmed_submitted: confirmed };
    if (resume !== (selected.tailoring_run_id || "")) body.tailoring_run_id = resume || null;
    if (appliedAt !== localDate(selected.applied_at)) body.applied_at = appliedAt ? new Date(appliedAt).toISOString() : null;
    try { open(await personal<Application>(`/applications/${selected.id}`, "PATCH", body)); await load(); setNotice("Application updated."); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }
  return <div className="space-y-7">
    <div><h1 className="font-serif text-4xl">Your applications</h1><p className="mt-2 max-w-2xl text-ink-secondary">Track submissions, interviews, follow-ups, and the resume you used. Update each status after taking the action.</p></div>
    {error && <p role="alert" className="rounded border border-bad/30 p-3 text-bad">{error}</p>}
    {notice && <p role="status" className="border-l-2 border-accent pl-3 text-sm">{notice}</p>}
    <div className="flex flex-wrap gap-3">{statuses.map(value => <button key={value} onClick={() => setFilter(value)} className={`rounded border p-3 text-sm capitalize ${filter === value ? "border-accent text-accent" : "border-rule"}`}>{value} <span className="ml-2 tabular-nums">{ledger?.counts[value] || 0}</span></button>)}</div>
    <div className="grid gap-3 sm:grid-cols-2"><input aria-label="Search applications" className={input} placeholder="Search role or company" value={q} onChange={e => setQ(e.target.value)} /><select aria-label="Application status filter" className={input} value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All applications</option>{statuses.map(value => <option key={value} value={value}>{value}</option>)}</select></div>
    {selected && <Section title={`${selected.company} · ${selected.title}`} action={<button className="text-sm underline" onClick={() => setSelected(null)}>Close details</button>}>
      <form onSubmit={save} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="space-y-1 text-sm">Application status<select aria-label="Application status" className={input} value={status} onChange={e => { setStatus(e.target.value); setConfirmed(false); }}>{statuses.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
          <label className="space-y-1 text-sm">Next action date<input type="datetime-local" className={input} value={nextAction} onChange={e => setNextAction(e.target.value)} /></label>
          <label className="space-y-1 text-sm">Submitted at<input type="datetime-local" className={input} value={appliedAt} onChange={e => setAppliedAt(e.target.value)} /></label>
          <label className="space-y-1 text-sm">Resume used<select aria-label="Resume used" className={input} value={resume} onChange={e => setResume(e.target.value)}><option value="">No resume pinned</option>{runs.map(run => <option key={run.id} value={run.id}>{run.label} · {run.id.slice(0, 8)}</option>)}</select></label>
        </div>
        <p className="text-xs text-ink-tertiary">A pinned resume must be ready and match this job description. Existing pinned versions remain available when your master changes.</p>
        <label className="block space-y-1 text-sm">Notes<textarea aria-label="Notes" className={input} rows={4} maxLength={10000} value={notes} onChange={e => setNotes(e.target.value)} /></label>
        {((status === "applied" && selected.status !== "applied") || (!selected.applied_at && !!appliedAt)) && <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} className="mt-1" />I submitted this application and want to record it.</label>}
        <div className="flex flex-wrap items-center gap-4"><Button type="submit" disabled={busy}>Save application</Button><a href={selected.apply_url} target="_blank" rel="noreferrer" className="text-sm text-accent underline">Open original application ↗</a>{selected.resume_pdf_url && <a href={artifactUrl(selected.resume_pdf_url)} target="_blank" rel="noreferrer" className="text-sm text-accent underline">Download pinned resume</a>}</div>
      </form>
      <details><summary className="cursor-pointer text-sm">Activity history</summary><ol className="mt-3 space-y-2">{selected.history?.map(event => <li key={event.id} className="border-l border-rule pl-3 text-sm"><p>{event.event_type === "created" ? "Added to tracker" : event.from_status !== event.to_status ? `${event.from_status} → ${event.to_status}` : "Details updated"}</p><p className="mt-1 text-xs text-ink-tertiary">{display(event.created_at)}{event.detail.changed_fields?.length ? " · " + event.detail.changed_fields.join(", ") : ""}</p></li>)}</ol></details>
    </Section>}
    <div className="space-y-3">{ledger?.items.map(item => <article key={item.id} className="rounded border border-rule p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl">{item.title}</h2><p className="mt-1 text-sm text-ink-secondary">{item.company} · {item.location || "Location not supplied"}</p></div><span className="text-sm capitalize text-accent">{item.status}</span></div><p className="mt-3 text-xs text-ink-tertiary">Submitted: {display(item.applied_at)} · Next action: {display(item.next_action_at)}{item.job_status !== "open" ? " · Source no longer lists this opening" : ""}</p><div className="mt-4 flex flex-wrap gap-4"><Button variant="secondary" disabled={busy} onClick={() => details(item.id)}>Update application</Button>{item.resume_pdf_url && <a href={artifactUrl(item.resume_pdf_url)} target="_blank" rel="noreferrer" className="self-center text-sm text-accent underline">Resume used</a>}</div></article>)}</div>
    {ledger && !ledger.items.length && <p className="border-y border-rule py-10 text-center text-ink-secondary">No applications in this view. <Link href="/jobs" className="text-accent underline">Find a job</Link> and choose Track application.</p>}
    <p className="text-xs text-ink-tertiary">Following a link or using autofill does not mark an application as submitted. The history records your explicit edits; CareerOS does not submit forms.</p>
  </div>;
}
