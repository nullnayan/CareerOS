"use client";
import { useEffect, useState } from "react";
import { useWorkspace } from "../context/WorkspaceContext";
import { personal } from "../lib/personal";
import { Button, Section } from "../components/ui";

export default function SettingsPage() {
  const { user, reload } = useWorkspace();
  const [owners, setOwners] = useState<{ id: string; email: string }[]>([]);
  const [error, setError] = useState("");
  const [routing, setRouting] = useState<{ groups: { group: string; variable: string; configured: boolean; tasks: string[]; independent_organization_backups?: boolean; backup_variables?: string[] }[]; models: Record<string, string>; embeddings: { model: string } } | null>(null);
  useEffect(() => { personal<typeof owners>("/workspace/owners").then(setOwners).catch(e => setError(e.message)); }, []);
  useEffect(() => { if (user) personal<NonNullable<typeof routing>>("/workspace/ai-routing").then(setRouting).catch(e => setError(e.message)); }, [user]);
  async function choose(id: string) {
    try { await personal("/workspace/owner", "POST", { owner_id: id }); setOwners([]); reload(); } catch (e: any) { setError(e.message); }
  }
  async function createNew() {
    try { await personal("/workspace/owner", "POST", { create_new: true }); setOwners([]); reload(); } catch (e: any) { setError(e.message); }
  }
  return <div className="space-y-7"><h1 className="font-serif text-4xl">Personal workspace</h1>
    {error && <p role="alert" className="text-bad">{error}</p>}
    <Section title="Local owner" description="CareerOS opens without a login. Existing records stay linked to one selected owner.">
      {user ? <p>Selected workspace: {user.email}</p> : owners.length ? owners.map(owner => <div key={owner.id} className="flex justify-between border-b border-rule py-3"><span>{owner.email}</span><Button onClick={() => choose(owner.id)}>Use this workspace</Button></div>) : <p>Start the backend and apply the database migration if the workspace is unavailable.</p>}
      {!user && <Button variant="secondary" onClick={createNew}>Create a fresh local workspace</Button>}
      <p className="text-sm text-ink-tertiary">Runs locally on this computer. API credentials stay on the backend. Job-search preferences are available under Jobs.</p>
    </Section>
    {routing && <Section title="AI task routing" description="Five separate Groq credentials assigned by job. Key values stay on the backend.">
      <div className="divide-y divide-rule">{routing.groups.map(group => <div key={group.group} className="py-3"><div className="flex items-center justify-between gap-3"><h3 className="capitalize">{group.group}</h3><span className={group.configured ? "text-good" : "text-bad"}>{group.configured ? "Primary configured" : "Primary missing"}</span></div><p className="mt-1 text-xs text-ink-tertiary">{group.variable}</p><p className="mt-2 text-sm text-ink-secondary">{group.tasks.join(", ")}</p>{group.independent_organization_backups && <details className="mt-2 text-sm"><summary className="cursor-pointer text-good">{group.backup_variables?.length || 0} configured independent-organization backups</summary><p className="mt-2 break-words text-xs text-ink-tertiary">{group.backup_variables?.join(", ")}</p></details>}</div>)}</div>
      <p className="text-sm text-ink-secondary">Text and vision use Groq. Embeddings run locally with {routing.embeddings.model}. {routing.groups.some(group => group.independent_organization_backups) ? "Keys confirmed to belong to independent organizations are used as backups on rate limits. Cooling keys are skipped; if every key is limited, CareerOS reports the earliest retry time." : "Keys sharing an organization share its limits; CareerOS waits rather than treating them as extra quota."}</p>
    </Section>}
  </div>;
}
