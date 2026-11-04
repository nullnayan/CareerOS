"use client";
import { FormEvent, useEffect, useState } from "react";
import { Button, Section } from "../components/ui";
import { personal } from "../lib/personal";

type Connection = { id: string; enabled: boolean; health: string; last_error?: string; last_checked_at?: string; retry_at?: string };
type Source = { key: string; name: string; tool: string; url: string; scope: string; limitation: string; connectable: boolean; verification: string; connection?: Connection };
type Data = { engine: string; sources: Source[]; archived: { id: string; company: string; provider: string }[]; runtime: Record<string, { installed: boolean; version: string; check: string }>; coverage: { employers: { name: string; state: string; outstanding_input: string }[]; sources: { id: string; name: string; state: string; outstanding_input: string }[] } };

export default function OSSConnectionsPanel({ onChange }: { onChange: () => Promise<void> }) {
  const [data, setData] = useState<Data | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  async function load() { setData(await personal<Data>("/jobs/oss")); }
  useEffect(() => { load().catch(e => setMessage(e.message)); }, []);
  async function connect(source: Source) {
    setBusy(source.key); setMessage("");
    try {
      if (source.connection) await personal(`/jobs/sources/${source.connection.id}`, "PATCH", { enabled: !source.connection.enabled });
      else await personal("/jobs/oss/connections", "POST", { key: source.key });
      setMessage("Connection saved. Discovery waits for Search jobs; schedules and preferences were preserved.");
      await load(); await onChange();
    } catch (e: any) { setMessage(e.message); } finally { setBusy(""); }
  }
  async function addEmployer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    setBusy("employer"); setMessage("");
    try {
      await personal("/jobs/oss/employer", "POST", { company: form.get("company"), url: form.get("url") });
      setMessage("Employer board saved for ats-scrapers. It will be checked only when you search.");
      await load(); await onChange();
    } catch (e: any) { setMessage(e.message); } finally { setBusy(""); }
  }
  return <div className="space-y-6">
    <Section title="Open-source job discovery" description="JobSpy, ats-scrapers, selected OmkarCloud collectors and Crawl4AI. Existing custom collectors are archived and cannot run in this mode.">
      {message && <p role="status" className="text-sm">{message}</p>}
      <p className="text-sm text-ink-secondary">Choose sources for your next search. Installed software and a saved connection do not establish live website coverage. Source restrictions and country limits still apply.</p>
      <details><summary className="cursor-pointer text-sm">Collector installation status</summary><div className="mt-2 space-y-2">{Object.entries(data?.runtime || {}).map(([tool, runtime]) => <p key={tool} className="break-words text-xs">{tool}: {runtime.installed ? "Interpreter installed" : "Runtime missing"} · {runtime.version}. {runtime.check}</p>)}</div></details>
      {!data && <p>Loading source setup…</p>}
      <div className="grid gap-3 sm:grid-cols-2">{data?.sources.map(source => <div key={source.key} className="min-w-0 space-y-2 rounded border border-rule p-3">
        <strong>{source.name}</strong><p className="text-xs text-ink-tertiary">{source.tool} · Verification: {source.verification.replaceAll("_", " ")}</p>
        <p className="text-sm">{source.scope}</p><p className="text-xs text-ink-secondary">{source.limitation}</p>
        <p className="text-xs">{source.connection ? `${source.connection.enabled ? "Enabled" : "Disabled"} · ${source.connection.health || "never checked"}` : "Not connected"}</p>
        {source.connection?.last_checked_at && <p className="text-xs">Last check: {new Date(source.connection.last_checked_at + "Z").toLocaleString()}</p>}
        {source.connection?.retry_at && <p className="text-xs">Next allowed check: {new Date(source.connection.retry_at + "Z").toLocaleString()}</p>}
        {source.connection?.last_error && <p className="text-xs text-bad">{source.connection.last_error}</p>}
        <div className="flex flex-wrap items-center gap-3"><Button variant="secondary" disabled={!!busy || !source.connectable || !data.runtime[source.tool]?.installed} onClick={() => connect(source)}>{source.connection ? source.connection.enabled ? "Disable source" : "Enable source" : "Connect source"}</Button><a href={source.url} target="_blank" rel="noreferrer" className="text-sm text-accent underline">Original site ↗</a></div>
      </div>)}</div>
    </Section>
    <Section title="Connect another employer with ats-scrapers" description="Supply its exact public ATS board URL. The upstream library must support that board; saving it does not verify live access.">
      <form onSubmit={addEmployer} className="space-y-3">
        <label className="block text-sm">Employer name<input name="company" required maxLength={150} className="mt-1 block w-full rounded border border-rule p-2" /></label>
        <label className="block text-sm">Public ATS board URL<input name="url" type="url" required maxLength={2000} className="mt-1 block w-full rounded border border-rule p-2" /></label>
        <Button disabled={!!busy} type="submit">Connect with ats-scrapers</Button>
      </form>
    </Section>
    <Section title="Full source inventory" description="Retained targets include sources without working automatic access. Legacy probe evidence is historical and does not verify the new engine.">
      <details><summary className="cursor-pointer text-sm">Review all {data?.coverage.sources.length || 0} source targets and blockers</summary><div className="mt-3 space-y-3">{data?.coverage.sources.map(source => <div key={source.id} className="border-b border-rule pb-2"><strong className="text-sm">{source.name}</strong><p className="text-xs">{source.state} · {source.outstanding_input}</p></div>)}</div></details>
      <details><summary className="cursor-pointer text-sm">Review {data?.coverage.employers.length || 0} employer candidates</summary><div className="mt-3 space-y-3">{data?.coverage.employers.map(employer => <div key={employer.name}><strong className="text-sm">{employer.name}</strong><p className="text-xs">{employer.state} · {employer.outstanding_input}</p></div>)}</div></details>
      <details><summary className="cursor-pointer text-sm">Archived legacy connections ({data?.archived.length || 0})</summary><p className="my-2 text-sm">Retained for administrative rollback. These collectors cannot run in open-source mode.</p>{data?.archived.map(source => <p key={source.id} className="text-xs">{source.company} · {source.provider}</p>)}</details>
    </Section>
  </div>;
}
