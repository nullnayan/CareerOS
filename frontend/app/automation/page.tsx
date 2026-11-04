"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Button, Section } from "../components/ui";
import { personal } from "../lib/personal";

type Settings = {
  enabled: boolean;
  interval_minutes: number;
  prepare_resumes: boolean;
  max_preparations: number;
  minimum_score: number;
  daily_pdf_limit: number;
};
type Task = {
  id: string; kind: string; status: string; attempts: number;
  error: string | null; created_at: string; finished_at: string | null;
  payload: Record<string, unknown>; result: Record<string, unknown> | null;
};
type Status = {
  settings: Settings; next_run_at: string | null; last_run_at: string | null;
  worker: { heartbeat_at: string | null; running: boolean };
  tasks: Task[];
  daily_prepared?: number;
};

const initial: Settings = { enabled: false, interval_minutes: 60, prepare_resumes: true, max_preparations: 5, minimum_score: 60, daily_pdf_limit: 5 };
const input = "w-full min-w-0 rounded border border-rule bg-surface p-2.5 text-sm text-ink";
function date(value: string | null | undefined) {
  if (!value) return "Not yet";
  const normalized = /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : value + "Z";
  return new Date(normalized).toLocaleString();
}
function taskTitle(task: Task) {
  if (task.kind === "discover" || task.kind === "discovery" || task.kind === "refresh") return "Discover jobs";
  if (task.kind === "prepare" || task.kind === "prepare_resume") return "Prepare resume";
  return task.kind.replaceAll("_", " ");
}

export default function AutomationPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [settings, setSettings] = useState<Settings>(initial);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loaded, setLoaded] = useState(false);
  const dirty = useRef(false);

  async function load() {
    const data = await personal<Status>("/automation");
    setStatus(data);
    if (!dirty.current) setSettings(data.settings);
    setLoaded(true);
  }
  useEffect(() => {
    let alive = true;
    const refresh = () => {
      if (!alive || document.hidden) return;
      load().catch(e => { if (alive) setError(e.message); });
    };
    refresh();
    const timer = setInterval(refresh, 10000);
    document.addEventListener("visibilitychange", refresh);
    return () => { alive = false; clearInterval(timer); document.removeEventListener("visibilitychange", refresh); };
  }, []);
  function field<K extends keyof Settings>(name: K, value: Settings[K]) {
    dirty.current = true;
    setSettings(s => ({ ...s, [name]: value }));
  }
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy("Saving schedule"); setError(""); setNotice("");
    try {
      await personal("/automation/settings", "PUT", settings);
      dirty.current = false;
      await load();
      setNotice(settings.enabled ? "Schedule saved. Jobs will refresh while the worker is running." : "Schedule paused. Already queued work remains visible below.");
    } catch (e: any) { setError(e.message); } finally { setBusy(""); }
  }
  async function run() {
    setBusy("Queuing discovery"); setError(""); setNotice("");
    try { await personal("/automation/run", "POST"); await load(); setNotice("Discovery queued. You can leave this page while the worker processes it."); }
    catch (e: any) { setError(e.message); } finally { setBusy(""); }
  }
  async function retry(task: Task) {
    setBusy("Retrying task"); setError(""); setNotice("");
    try { await personal(`/automation/tasks/${task.id}/retry`, "POST"); await load(); setNotice("Task queued for another attempt."); }
    catch (e: any) { setError(e.message); } finally { setBusy(""); }
  }
  async function cancel(task: Task) {
    setBusy("Cancelling task"); setError(""); setNotice("");
    try { await personal(`/automation/tasks/${task.id}/cancel`, "POST"); await load(); setNotice("Task cancelled. Running discovery collectors are signalled to stop."); }
    catch (e: any) { setError(e.message); } finally { setBusy(""); }
  }
  const pending = status?.tasks.filter(t => ["queued", "pending", "running", "retry"].includes(t.status)).length || 0;

  return <div className="space-y-8">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div><h1 className="font-serif text-4xl">Job automation</h1><p className="mt-2 max-w-2xl text-ink-secondary">Keep discovery and resume preparation moving in the background, with a visible queue and a history of each attempt.</p></div>
      <Button disabled={!!busy || !loaded} onClick={run}>Run discovery now</Button>
    </div>
    <nav aria-label="Job tools" className="flex flex-wrap gap-5 text-sm"><Link href="/jobs" className="text-accent underline">Discover jobs</Link><Link href="/applications" className="text-accent underline">Applications</Link><Link href="/master" className="text-accent underline">Master resume</Link><Link href="/autofill" className="text-accent underline">Browser autofill</Link></nav>
    {error && <p role="alert" className="whitespace-pre-wrap rounded border border-bad/30 p-3 text-bad">{error}</p>}
    {notice && <p role="status" className="border-l-2 border-accent pl-3 text-sm">{notice}</p>}
    {busy && <p role="status" className="text-sm text-accent">{busy}…</p>}
    {!loaded && !error && <p className="text-ink-secondary">Loading automation…</p>}
    {status && <div className="grid gap-4 border-y border-rule py-4 text-sm sm:grid-cols-3">
      <div><p className="text-ink-tertiary">Worker</p><p className={status.worker.running ? "text-good" : "text-warn"}>{status.worker.running ? "Running" : "Not running"}</p><p className="mt-1 text-xs text-ink-tertiary">Last heartbeat: {date(status.worker.heartbeat_at)}</p></div>
      <div><p className="text-ink-tertiary">Discovery schedule</p><p>{status.settings.enabled ? `Every ${status.settings.interval_minutes} minutes` : "Paused"}</p><p className="mt-1 text-xs text-ink-tertiary">Next: {status.settings.enabled ? date(status.next_run_at) : "Paused"}</p></div>
      <div><p className="text-ink-tertiary">Queue</p><p>{pending} unfinished tasks</p><p className="mt-1 text-xs text-ink-tertiary">Last discovery: {date(status.last_run_at)}</p>{typeof status.daily_prepared === "number" && <p className="mt-1 text-xs text-ink-tertiary">Prepared today: {status.daily_prepared} / {status.settings.daily_pdf_limit}</p>}</div>
    </div>}
    <Section title="Discovery schedule" description="Save your job preferences and connect sources on the Jobs page first. Scheduling is off until you enable it.">
      <form onSubmit={save} className="space-y-5">
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.enabled} disabled={!loaded || !!busy} onChange={e => field("enabled", e.target.checked)} />Enable scheduled discovery</label>
        <div className="grid gap-5 sm:grid-cols-3">
          <label className="space-y-1 text-sm">Refresh interval, minutes<input className={input} type="number" min={15} max={1440} required value={settings.interval_minutes} onChange={e => field("interval_minutes", Number(e.target.value))} /></label>
          <label className="space-y-1 text-sm">Maximum pending resume preparations<input className={input} type="number" min={1} max={20} required value={settings.max_preparations} onChange={e => field("max_preparations", Number(e.target.value))} /></label>
          <label className="space-y-1 text-sm">Daily PDF limit<input className={input} type="number" min={1} max={20} required value={settings.daily_pdf_limit} onChange={e => field("daily_pdf_limit", Number(e.target.value))} /></label>
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.prepare_resumes} disabled={!loaded || !!busy} onChange={e => field("prepare_resumes", e.target.checked)} />Queue resume preparation after discovery</label>
        <p className="max-w-3xl text-sm leading-relaxed text-ink-secondary">Preparation uses your active master and previously confirmed skills. New skills remain in the skill review for your confirmation. Incomplete job descriptions, closed openings, and jobs outside your requirements are not prepared automatically.</p>
        <Button type="submit" disabled={!!busy || !loaded}>Save automation settings</Button>
      </form>
    </Section>
    {status && !status.worker.running && <Section title="Start the worker"><p className="text-sm text-ink-secondary">Keep a separate terminal open in the backend folder. Saved schedules and queued tasks persist when the worker stops.</p><pre className="overflow-x-auto rounded border border-rule bg-surface p-3 text-xs">{'.\\venv\\Scripts\\python.exe -m automation.worker'}</pre></Section>}
    <Section title="Recent tasks" description="Tasks survive restarts. Failed attempts keep their error and can be retried.">
      {!status?.tasks.length && <p className="border-y border-rule py-8 text-center text-ink-secondary">No automation tasks yet. Run discovery now or save an enabled schedule.</p>}
      <div className="space-y-3">{status?.tasks.map(task => <article key={task.id} className="space-y-3 rounded border border-rule bg-surface p-4">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><h3>{taskTitle(task)}</h3><p className="mt-1 text-xs text-ink-tertiary">Queued {date(task.created_at)} · {task.attempts} attempt{task.attempts === 1 ? "" : "s"}</p></div><span className={`text-sm capitalize ${task.status === "failed" ? "text-bad" : task.status === "succeeded" || task.status === "ready" ? "text-good" : "text-ink-secondary"}`}>{task.status.replaceAll("_", " ")}</span></div>
        {typeof task.payload?.job_id === "string" && <p className="break-all text-xs text-ink-tertiary">Job {task.payload.job_id}</p>}
        {task.error && <p className="whitespace-pre-wrap break-words text-sm text-bad">{task.error}</p>}
        {task.result && <div className="space-y-2 text-sm text-ink-secondary">{typeof task.result.message === "string" && <p>{task.result.message}</p>}{typeof task.result.listed === "number" && <p>{task.result.listed} listings checked · {typeof task.result.new === "number" ? task.result.new : 0} new</p>}{typeof task.result.run_id === "string" && <Link href={`/tailor?run=${task.result.run_id}`} className="inline-block text-accent underline">Open resume skill review →</Link>}</div>}
        {Array.isArray(task.result?.awaiting_confirmation) && !!task.result.awaiting_confirmation.length && <p className="text-sm text-warn">Skills awaiting your confirmation: {task.result.awaiting_confirmation.join(", ")}</p>}
        {task.finished_at && <p className="text-xs text-ink-tertiary">Finished {date(task.finished_at)}</p>}
        {task.status === "failed" && <Button variant="secondary" disabled={!!busy} onClick={() => retry(task)}>Retry task</Button>}
        {(task.status === "queued" || (task.kind === "discover" && task.status === "running")) && <Button variant="ghost" disabled={!!busy} onClick={() => cancel(task)}>Cancel task</Button>}
      </article>)}</div>
    </Section>
  </div>;
}
