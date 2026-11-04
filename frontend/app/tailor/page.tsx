"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, Section } from "../components/ui";
import { Master, TailoringRun, artifactUrl, personal } from "../lib/personal";

export default function TailorPage() {
  const [masters, setMasters] = useState<Master[]>([]);
  const [runs, setRuns] = useState<TailoringRun[]>([]);
  const [run, setRun] = useState<TailoringRun | null>(null);
  const [jd, setJd] = useState("");
  const [label, setLabel] = useState("");
  const [useAI, setUseAI] = useState(false);
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const [categories, setCategories] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const master = masters.find(m => m.status === "active");
  const runMaster = masters.find(m => m.id === run?.master_id);
  async function load(requestedRun = false) {
    try {
      const [m, r] = await Promise.all([personal<Master[]>("/tailor/masters"), personal<TailoringRun[]>("/tailor/runs")]);
      setMasters(m); setRuns(r);
      const requested = new URLSearchParams(window.location.search).get("run");
      const found = r.find(item => item.id === requested);
      if (requestedRun && found) open(found);
    } catch (e: any) { setError(e.message); }
  }
  useEffect(() => { load(true); }, []);
  function open(item: TailoringRun) {
    setRun(item);
    setJd(item.job_description || ""); setLabel(item.label);
    setConfirmed(Object.fromEntries(item.candidates.map(c => [c.canonical, c.confirmed])));
    setCategories(Object.fromEntries(item.candidates.map(c => [c.canonical, c.category])));
    setError("");
  }
  async function analyze() {
    if (!master) return;
    setBusy("Finding missing skills"); setError("");
    try {
      const item = await personal<TailoringRun>("/tailor/analyze", "POST", { master_id: master.id, job_description: jd, label: label.trim() || "Tailored resume", use_ai: useAI });
      open(item); await load();
    } catch (e: any) { setError(e.message); } finally { setBusy(""); }
  }
  async function prepare() {
    if (!run) return;
    setBusy("Compiling and validating your PDF"); setError("");
    try {
      const selected = run.candidates.filter(c => confirmed[c.canonical]).map(c => ({ canonical: c.canonical, category: categories[c.canonical] }));
      const item = await personal<TailoringRun>(`/tailor/runs/${run.id}/prepare`, "POST", { confirmed_skills: selected });
      setRun(item); await load();
    } catch (e: any) { setError(e.message); await load(); } finally { setBusy(""); }
  }
  async function reviewAgain() {
    if (!run) return;
    setBusy("Starting a fresh skill review"); setError("");
    try { const item = await personal<TailoringRun>(`/tailor/runs/${run.id}/reanalyze`, "POST"); open(item); await load(); }
    catch (e: any) { setError(e.message); } finally { setBusy(""); }
  }
  const count = run?.candidates.filter(c => confirmed[c.canonical]).length || 0;
  return <div className="space-y-9">
    <div><h1 className="font-serif text-4xl">Tailor your resume</h1><p className="mt-2 max-w-2xl text-ink-secondary">Add up to five missing job-description skills to your master LaTeX. Projects, education, and existing skills stay intact.</p></div>
    {error && <p role="alert" className="whitespace-pre-wrap rounded border border-bad/30 p-4 text-bad">{error}</p>}
    {!master ? <Section title="Start with your master"><p>Import your .tex source, compile it, and review the baseline before tailoring.</p><Link href="/master" className="text-accent underline">Set up master resume →</Link></Section> :
      <Section title="Job description" description={`Active source: ${master.filename}`}>
        <label className="block space-y-2 text-sm"><span>Company and role</span><input value={label} onChange={e => setLabel(e.target.value)} maxLength={150} placeholder="Company · Graduate Backend Engineer" className="w-full rounded border border-rule bg-surface p-3" /></label>
        <label className="block space-y-2 text-sm"><span>Full job description</span><textarea value={jd} onChange={e => setJd(e.target.value)} rows={9} maxLength={50000} placeholder="Paste the complete requirements here…" className="w-full rounded border border-rule bg-surface p-3" /></label>
        <label className="flex items-start gap-2 text-sm text-ink-secondary"><input type="checkbox" checked={useAI} onChange={e => setUseAI(e.target.checked)} className="mt-1" /><span>Use the existing Groq connection for broader skill extraction. Leave off to use the local dictionary without API requests. No paid fallback is used.</span></label>
        <Button onClick={analyze} disabled={!!busy || jd.trim().length < 50}>Find missing skills</Button>
      </Section>}
    {busy && <p role="status" className="text-accent">{busy}…</p>}
    {run && <Section title={run.label} description={`Source revision ${run.master_id.slice(0, 8)} · ${run.status}`}>
      {run.status === "ready" && <div className="space-y-3"><p className="text-sm text-ink-secondary">This prepared draft is preserved. Start a fresh review to confirm additional suggestions or change your selection.</p><Button variant="secondary" onClick={reviewAgain} disabled={!!busy || !master}>Review skills again</Button></div>}
      {!run.candidates.length ? <p>All recognized requirements are already covered, or no additional technical skills were recognized. You can generate an unchanged copy.</p> : <div className="divide-y divide-rule border-y border-rule">
        {run.candidates.map(c => <div key={c.canonical} className="grid gap-3 py-4 md:grid-cols-[1fr_220px]">
          <div><label className="flex items-center gap-3 font-medium"><input type="checkbox" checked={!!confirmed[c.canonical]} disabled={!!busy || run.status === "ready"} onChange={e => setConfirmed(p => ({ ...p, [c.canonical]: e.target.checked }))} />{c.name}<span className="text-xs font-normal text-ink-tertiary">{c.importance}</span></label>
            <p className="ml-6 mt-1 text-xs text-ink-tertiary">{c.confirmed ? "Previously confirmed" : "Select only if you know this skill"}</p><p className="ml-6 mt-2 text-sm text-ink-secondary">{c.excerpt}</p></div>
          <label className="space-y-1 text-xs text-ink-tertiary"><span>Skills category</span><select aria-label={`Category for ${c.name}`} value={categories[c.canonical] || ""} disabled={!!busy || run.status === "ready"} onChange={e => setCategories(p => ({ ...p, [c.canonical]: e.target.value }))} className="w-full rounded border border-rule bg-surface p-2 text-sm text-ink"><option value="">Choose category</option>{runMaster?.categories.map(category => <option key={category}>{category}</option>)}</select></label>
        </div>)}
      </div>}
      {run.status !== "ready" && <div className="flex flex-wrap items-center gap-4"><Button onClick={prepare} disabled={!!busy || run.candidates.some(c => confirmed[c.canonical] && !categories[c.canonical])}>Generate PDF with {count} addition{count === 1 ? "" : "s"}</Button><p className="text-xs text-ink-tertiary">Selecting a skill confirms it for future jobs too.</p></div>}
      {run.diagnostics && <p className="whitespace-pre-wrap text-sm text-ink-secondary">{run.diagnostics}</p>}
      {!!run.changes?.length && <div className="space-y-4">{run.changes.map(change => <div key={change.category} className="rounded border border-rule p-4"><h3 className="font-medium">{change.category}</h3><pre className="mt-2 whitespace-pre-wrap text-xs text-ink-tertiary">Before: {change.before}</pre><pre className="mt-2 whitespace-pre-wrap text-xs text-good">After: {change.after}</pre></div>)}</div>}
      {run.pdf_url && <><div className="flex flex-wrap gap-5"><a href={artifactUrl(run.pdf_url) + "?download=true"} className="text-accent underline">Download PDF</a>{run.source_url && <a href={artifactUrl(run.source_url)} className="text-accent underline">Download LaTeX</a>}{run.project_url && <a href={artifactUrl(run.project_url)} className="text-accent underline">Download project ZIP</a>}</div><iframe title="Tailored resume PDF" src={artifactUrl(run.pdf_url)} className="h-[750px] w-full border border-rule" /></>}
    </Section>}
    {!!runs.length && <Section title="Previous analyses"><div className="divide-y divide-rule">{runs.map(item => <button key={item.id} disabled={!!busy} onClick={() => open(item)} className="flex w-full items-center justify-between gap-3 py-3 text-left hover:text-accent"><span>{item.label}<span className="ml-3 text-xs text-ink-tertiary">{new Date(item.created_at).toLocaleString()}</span></span><span className="text-sm">{item.status}</span></button>)}</div></Section>}
  </div>;
}
