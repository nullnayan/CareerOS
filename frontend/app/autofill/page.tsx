"use client";
import { FormEvent, useEffect, useState } from "react";
import { Button, Section } from "../components/ui";
import { personal } from "../lib/personal";

type Profile = { full_name: string; first_name: string; last_name: string; email: string; phone: string; location: string; linkedin: string; github: string; portfolio: string };
type Credential = { id: string; label: string; created_at: string; revoked_at: string | null };
const empty: Profile = { full_name: "", first_name: "", last_name: "", email: "", phone: "", location: "", linkedin: "", github: "", portfolio: "" };
const fields: [keyof Profile, string][] = [["full_name", "Full name"], ["first_name", "First / given name"], ["last_name", "Last / family name"], ["email", "Email"], ["phone", "Phone with country code"], ["location", "Current city / location"], ["linkedin", "LinkedIn URL"], ["github", "GitHub URL"], ["portfolio", "Portfolio URL"]];

export default function AutofillPage() {
  const [profile, setProfile] = useState<Profile>(empty);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [pairing, setPairing] = useState<{ code: string; expires_at: string } | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  async function loadCredentials() { setCredentials(await personal<Credential[]>("/autofill/credentials")); }
  useEffect(() => { Promise.all([personal<Profile>("/autofill/profile"), loadCredentials()]).then(([p]) => setProfile(p)).catch(e => setError(e.message)); }, []);
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try { setProfile(await personal<Profile>("/autofill/profile", "PUT", profile)); setNotice("Profile saved. The extension uses only these details when you request a preview."); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }
  async function pair() {
    setBusy(true); setError("");
    try { setPairing(await personal<{ code: string; expires_at: string }>("/autofill/pairings", "POST", {})); await loadCredentials(); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }
  async function revoke(id: string) {
    setBusy(true); setError("");
    try { await personal(`/autofill/credentials/${id}`, "DELETE"); await loadCredentials(); setNotice("Extension credential revoked."); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }
  return <div className="space-y-8">
    <div><h1 className="font-serif text-4xl">Application autofill</h1><p className="mt-2 max-w-2xl text-ink-secondary">Connect the browser extension, review basic fields, and choose what to fill. You review and submit every application.</p></div>
    {error && <p role="alert" className="whitespace-pre-wrap border-l-2 border-bad pl-3 text-bad">{error}</p>}
    {notice && <p role="status" className="border-l-2 border-accent pl-3 text-sm">{notice}</p>}
    <Section title="Your application profile" description="Leave anything you do not want shared blank. Split names are explicit so the extension never guesses how to divide your name."><form onSubmit={save} className="space-y-5"><div className="grid gap-4 sm:grid-cols-2">{fields.map(([key, label]) => <label key={key} className="space-y-1 text-sm">{label}<input value={profile[key]} onChange={e => setProfile(p => ({ ...p, [key]: e.target.value }))} type={key === "email" ? "email" : ["linkedin", "github", "portfolio"].includes(key) ? "url" : "text"} maxLength={key === "phone" ? 40 : key === "full_name" ? 150 : key.endsWith("name") ? 100 : ["email", "location"].includes(key) ? 200 : 500} className="w-full min-w-0 rounded border border-rule bg-surface p-2.5" /></label>)}</div><Button type="submit" disabled={busy}>Save application profile</Button></form></Section>
    <Section title="Install the Chrome / Edge extension" description="The extension is local and unpacked; no browser store account is needed."><ol className="list-decimal space-y-2 pl-5 text-sm text-ink-secondary"><li>Open <code>chrome://extensions</code> or <code>edge://extensions</code> and turn on Developer mode.</li><li>Choose Load unpacked and select <code className="break-all">C:\Users\nayan\Downloads\careeros_scaffold\careeros\extension</code>.</li><li>Generate a pairing code below. Open the CareerOS extension popup and paste the code.</li><li>Open an application page. Click Preview empty fields, review the values, and click Fill selected fields.</li></ol><p className="text-sm text-ink-secondary">The extension can save a reviewed job description from your current tab and download a prepared PDF. Upload the PDF yourself. Custom widgets, iframes, eligibility questions, and unsupported fields require manual entry.</p></Section>
    <Section title="Pair this browser" description="Each code expires after five minutes and can be used once. Generating another code replaces unused invitations."><Button onClick={pair} disabled={busy}>Generate pairing code</Button>{pairing && <div className="space-y-2 rounded border border-rule p-4"><label className="block text-sm">Copy this code into the extension<input readOnly value={pairing.code} onFocus={e => e.target.select()} className="mt-2 w-full min-w-0 rounded border border-rule bg-surface p-2 font-mono text-sm" /></label><p className="text-xs text-ink-tertiary">Expires {new Date(pairing.expires_at + "Z").toLocaleTimeString()}.</p><Button variant="secondary" onClick={async () => { try { await navigator.clipboard.writeText(pairing.code); setNotice("Pairing code copied."); } catch { setNotice("Select the code and copy it manually."); } }}>Copy code</Button></div>}</Section>
    <Section title="Connected browsers" action={<Button variant="secondary" disabled={busy} onClick={() => loadCredentials().catch(e => setError(e.message))}>Refresh</Button>}>{!credentials.length && <p className="text-sm text-ink-secondary">No extension credentials yet.</p>}{credentials.map(item => <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-rule py-3"><div><p>{item.label}</p><p className="text-xs text-ink-tertiary">{new Date(item.created_at + "Z").toLocaleString()} · {item.revoked_at ? "Revoked" : "Active"}</p></div>{!item.revoked_at && <Button disabled={busy} variant="secondary" onClick={() => revoke(item.id)}>Revoke access</Button>}</div>)}</Section>
  </div>;
}
