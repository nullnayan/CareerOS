"use client";
import { useState } from "react";
import { Button, Section } from "../components/ui";
import { personal } from "../lib/personal";

type Row = { row: number; site: string; title: string; company: string; location: string; url: string; description: string };
type Preview = { items: Row[]; errors: { row: number; message: string }[]; total_rows: number; note: string };

export default function ReviewedExportPanel({ onChange }: { onChange: () => Promise<void> }) {
  const [content, setContent] = useState("");
  const [format, setFormat] = useState("csv");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [full, setFull] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function read(file?: File) {
    setPreview(null); setSelected([]); setConfirmed(false); setFull(false); setMessage(""); setContent("");
    if (!file) return;
    if (file.size > 2_000_000) { setMessage("Use an export smaller than 2 MB, with at most 200 rows."); return; }
    setBusy(true);
    try {
      const text = await file.text(), kind = file.name.toLowerCase().endsWith(".json") ? "json" : "csv";
      const result = await personal<Preview>("/jobs/imports/preview", "POST", { content: text, format: kind });
      setContent(text); setFormat(kind); setPreview(result);
    } catch (e: any) { setMessage(e.message); } finally { setBusy(false); }
  }
  async function commit() {
    setBusy(true); setMessage("");
    try {
      const result = await personal<{ imported: number }>("/jobs/imports/commit", "POST", { content, format, rows: selected, confirmed, full_descriptions: full });
      setMessage(`${result.imported} selected records imported. Discovery remains under your search controls.`);
      setPreview(null); setSelected([]); setConfirmed(false); setFull(false); await onChange();
    } catch (e: any) { setMessage(e.message); } finally { setBusy(false); }
  }
  return <Section title="Review a community export" description="Import a JobSpy-compatible CSV or JSON you are permitted to use. CareerOS does not install or run JobSpy, log in, or scrape these boards.">
    <p className="text-xs text-ink-tertiary">Supported export sites: LinkedIn, Indeed, Glassdoor, ZipRecruiter, Bayt, Naukri, BDJobs and HelloWork. Coverage and country restrictions depend on the original source.</p>
    <label className="block text-sm">Export file<input type="file" accept=".csv,.json" disabled={busy} onChange={e => read(e.target.files?.[0])} className="mt-1 block w-full min-w-0 text-sm" /></label>
    {message && <p role="status" className="text-sm">{message}</p>}
    {preview && <div className="space-y-3">
      <p className="text-sm">{preview.items.length} valid of {preview.total_rows} supplied rows. Select up to 100 to import.</p>
      {!!preview.errors.length && <details><summary className="text-sm">{preview.errors.length} rows need attention</summary>{preview.errors.map(error => <p key={error.row} className="text-xs">Row {error.row + 1}: {error.message}</p>)}</details>}
      <div className="max-h-96 space-y-2 overflow-auto">{preview.items.map(row => <div key={row.row} className="rounded border border-rule p-3">
        <label className="flex gap-2 text-sm"><input type="checkbox" checked={selected.includes(row.row)} disabled={busy || (!selected.includes(row.row) && selected.length >= 100)} onChange={e => { setSelected(e.target.checked ? [...selected, row.row] : selected.filter(i => i !== row.row)); setFull(false); setConfirmed(false); }} />{row.title} · {row.company}</label>
        <p className="text-xs text-ink-tertiary">{row.site} · {row.location} · Description completeness unconfirmed</p>
        <details className="mt-2 text-sm"><summary>Review supplied description</summary><p className="whitespace-pre-wrap">{row.description}</p><a className="text-accent underline" href={row.url} target="_blank" rel="noreferrer">Original source</a></details>
      </div>)}</div>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={full} onChange={e => setFull(e.target.checked)} />I checked that every selected row contains the complete job description.</label>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />I reviewed these records and am permitted to import the selected content.</label>
      <Button disabled={busy || !confirmed || !selected.length} onClick={commit}>Import selected records ({selected.length})</Button>
    </div>}
  </Section>;
}
