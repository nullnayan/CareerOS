"use client";
import { FormEvent, useEffect, useState } from "react";
import { Button, Section } from "../components/ui";
import { personal } from "../lib/personal";
import ReviewedExportPanel from "./reviewed-export-panel";
import { Catalog } from "../lib/jobs";

const input = "w-full min-w-0 rounded border border-rule bg-surface p-2.5 text-sm text-ink";
type Connection = { id: string; name: string; implementation: string; conditions: string; community_status?: string; connection_state: string; next_action: string; required_input: string[]; website_url: string | null; enabled_connections: number; collects_automatically: boolean };

export default function ConnectionsPanel({ onChange }: { onChange: () => Promise<void> }) {
  const [entries, setEntries] = useState<Connection[]>([]);
  const [employers, setEmployers] = useState<NonNullable<Catalog["employer_reviews"]>>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function load() {
    const [data, catalog] = await Promise.all([personal<{ platforms: Connection[] }>("/jobs/connections"), personal<Catalog>("/jobs/catalog")]);
    setEntries(data.platforms); setEmployers(catalog.employer_reviews || []);
  }
  useEffect(() => { load().catch(e => setMessage(e.message)); }, []);
  async function connect() {
    setBusy(true); setMessage("");
    try { const result = await personal<{ added: unknown[] }>("/jobs/connections/free", "POST"); setMessage(`${result.added.length} new free connections saved. Search starts only when you click Search jobs.`); await onChange(); await load(); }
    catch (e: any) { setMessage(e.message); } finally { setBusy(false); }
  }
  async function addFeed(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget); setBusy(true); setMessage("");
    try { await personal("/jobs/sources/feed", "POST", { company: data.get("company"), feed_url: data.get("feed_url"), format: data.get("format"), full_descriptions: data.get("full") === "on" }); setMessage("Public feed connected. It will be checked during your next search."); await onChange(); await load(); }
    catch (e: any) { setMessage(e.message); } finally { setBusy(false); }
  }
  async function addEmployer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget); setBusy(true); setMessage("");
    try { await personal("/jobs/sources/employer", "POST", { provider: data.get("provider"), company: data.get("employer"), url: data.get("url"), access_reviewed: data.get("reviewed") === "on", full_descriptions: data.get("full") === "on" }); setMessage("Employer connection saved, never checked. Discovery waits for Search jobs."); await onChange(); await load(); }
    catch (e: any) { setMessage(e.message); } finally { setBusy(false); }
  }
  return <div className="space-y-6">
    <Section title="Source connections" description="Connect free sources now. Discovery waits for Search jobs.">
      <Button disabled={busy} onClick={connect}>Connect verified free sources</Button>
      {message && <p role="status" className="text-sm text-ink-secondary">{message}</p>}
      <div className="grid gap-3 sm:grid-cols-2">{entries.map(entry => <div key={entry.id} className="min-w-0 rounded border border-rule p-3">
        <strong>{entry.name}</strong><p className="text-xs text-ink-tertiary">{entry.connection_state.replaceAll("_", " ")}{entry.enabled_connections ? ` · ${entry.enabled_connections} enabled` : ""}</p>
        <p className="text-xs text-ink-tertiary">Implementation: {entry.implementation.replaceAll("_", " ")}. Live health appears on each configured source.</p>
        <p className="mt-1 text-xs text-ink-secondary">{entry.conditions}</p>
        <p className="mt-2 text-sm text-ink-secondary">{entry.next_action}</p>
        {!!entry.required_input.length && <p className="mt-1 text-xs text-ink-tertiary">For background collection: {entry.required_input.join("; ")}</p>}
        {entry.website_url && <a href={entry.website_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-sm text-accent underline">Open original site ↗</a>}
      </div>)}</div>
    </Section>
    <Section title="Connect an employer’s public feed" description="Use a published RSS, Atom, XML, JSON or JobPosting feed. CareerOS reads this feed without following application links.">
      <form onSubmit={addFeed} className="space-y-3"><div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">Employer or source<input name="company" required maxLength={150} className={input} /></label>
        <label className="text-sm">Public HTTPS feed URL<input name="feed_url" type="url" required maxLength={2000} className={input} /></label>
        <label className="text-sm">Feed format<select name="format" className={input}><option value="auto">Detect format</option><option value="xml">RSS / Atom / XML</option><option value="json">Job JSON</option><option value="jsonld">Page with JobPosting data</option></select></label>
      </div><label className="flex gap-2 text-sm"><input name="full" type="checkbox" />This feed provides complete job descriptions.</label>
      <Button type="submit" disabled={busy}>Connect public feed</Button></form>
    </Section>
    <Section title="Connect an enterprise employer" description="Workday uses an undocumented public career-site transport tested with fixtures. Taleo, SAP, Oracle and iCIMS require an explicit employer-published feed; their authenticated enterprise APIs are not connected.">
      <form onSubmit={addEmployer} className="space-y-3"><div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">Employer route<select name="provider" className={input}><option value="workday">Workday external career site</option><option value="taleo">Taleo RSS (up to 10 excerpts)</option><option value="sap_successfactors">SAP SuccessFactors published XML</option><option value="oracle_recruiting">Oracle employer-published feed</option><option value="icims">iCIMS employer-published feed</option></select></label>
        <label className="text-sm">Employer name<input name="employer" required maxLength={150} className={input} /></label>
        <label className="text-sm sm:col-span-2">Exact public site or feed URL<input name="url" type="url" required maxLength={2000} className={input} /></label>
      </div><label className="flex gap-2 text-sm"><input name="reviewed" type="checkbox" required />I reviewed this employer’s access conditions and this URL is published for public collection.</label>
      <label className="flex gap-2 text-sm"><input name="full" type="checkbox" />The published feed supplies complete descriptions (Taleo RSS always stays excerpts).</label>
      <Button type="submit" disabled={busy}>Connect employer route</Button></form>
    </Section>
    <ReviewedExportPanel onChange={onChange} />
    <Section title="Employer mapping review" description="Every employer candidate is retained. An official careers link does not establish a working ATS connection.">
      <details><summary className="cursor-pointer text-sm">Review {employers.length} employer candidates and prerequisites</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">{employers.map(row => <div key={row.company} className="min-w-0 rounded border border-rule p-3">
          <strong>{row.company}</strong><p className="text-xs text-ink-tertiary">{row.mapping_status.replaceAll("_", " ")}</p>
          <p className="mt-1 text-sm">{row.required_input}</p>
          {row.official_url && <a className="text-sm text-accent underline" href={row.official_url} target="_blank" rel="noreferrer">Official careers ↗</a>}
        </div>)}</div>
      </details>
    </Section>
  </div>;
}
