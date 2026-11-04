"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Button } from "../components/ui";
import { Master, artifactUrl, personal } from "../lib/personal";

type CompileResult = { master: Master; repaired: boolean; message: string };

const field = "block w-full min-w-0 rounded border border-rule bg-surface p-3 text-sm";
function message(error: unknown) {
  const text = error instanceof Error ? error.message : "Please try again.";
  return /failed to fetch|networkerror|network request failed/i.test(text)
    ? "CareerOS could not connect. Start the backend, then try again."
    : text;
}

export default function MasterPage() {
  const [mode, setMode] = useState("file");
  const [source, setSource] = useState("");
  const [master, setMaster] = useState<Master | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const acceptInitialLoad = useRef(true);

  useEffect(() => {
    let active = true;
    personal<Master | null>("/tailor/master")
      .then(item => { if (active && acceptInitialLoad.current) setMaster(item); })
      .catch(error => { if (active && acceptInitialLoad.current) setError(message(error)); });
    return () => { active = false; };
  }, []);

  async function compile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    acceptInitialLoad.current = false;
    setBusy("compile"); setError(""); setNotice(""); setMaster(null);
    const form = new FormData(event.currentTarget);
    const reference = form.get("reference") as File | null;
    if (!reference?.size) form.delete("reference");
    if (mode === "paste") form.set("source", source);
    try {
      const result = await personal<CompileResult>("/tailor/compile-resume", "POST", form);
      if (!result.master.pdf_url) throw new Error("A PDF could not be generated. Please check your LaTeX and try again.");
      setMaster(result.master);
      setNotice(result.message || "Your resume is ready to review.");
    } catch (error) { setError(message(error)); } finally { setBusy(""); }
  }

  async function activate() {
    if (!master) return;
    setBusy("activate"); setError(""); setNotice("");
    try {
      setMaster(await personal<Master>(`/tailor/masters/${master.id}/activate`, "POST"));
      setNotice("This resume will be used for future tailoring.");
    } catch (error) { setError(message(error)); } finally { setBusy(""); }
  }

  async function download(kind: "pdf" | "source") {
    if (!master) return;
    setError("");
    try {
      const path = kind === "pdf" ? master.pdf_url : `/tailor/masters/${master.id}/source`;
      if (!path) return;
      const response = await fetch(artifactUrl(path));
      if (!response.ok) throw new Error("The download is unavailable. Please try again.");
      const objectUrl = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = master.filename.replace(/\.(tex|zip)$/i, "") + (kind === "pdf" ? ".pdf" : ".tex");
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (error) { setError(message(error)); }
  }

  return <div className="space-y-8">
    <div><h1 className="font-serif text-4xl">Master resume</h1><p className="mt-2 max-w-2xl text-ink-secondary">Upload or paste your LaTeX to generate your resume. Your template stays intact. Add a reference PDF if you have one.</p></div>

    <form onSubmit={compile} className="space-y-5">
      <div className="flex gap-5 border-b border-rule" role="tablist" aria-label="LaTeX input method">
        {[["file", "Upload LaTeX file"], ["paste", "Paste LaTeX code"]].map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={mode === value} disabled={!!busy} onClick={() => setMode(value)} className={`border-b-2 pb-3 text-sm ${mode === value ? "border-accent text-accent" : "border-transparent text-ink-secondary"}`}>{label}</button>)}
      </div>

      {mode === "file" ? <label className="block space-y-2 text-sm"><span className="block">LaTeX file (.tex)</span><input name="file" type="file" accept=".tex" required disabled={!!busy} className="block w-full text-sm" /></label> : <label className="block space-y-2 text-sm"><span>LaTeX code</span><textarea name="source" aria-label="LaTeX code" value={source} onChange={event => setSource(event.target.value)} rows={16} required spellCheck={false} autoCapitalize="off" autoCorrect="off" disabled={!!busy} placeholder={"\\documentclass{article}\n...\n\\begin{document}\n...\n\\end{document}"} className={`${field} font-mono text-xs leading-relaxed`} /></label>}

      <label className="block space-y-2 text-sm"><span className="block">Resume PDF (optional)</span><input name="reference" type="file" accept=".pdf" disabled={!!busy} className="block w-full text-sm" /></label>
      <Button type="submit" disabled={!!busy || (mode === "paste" && !source.trim())}>{busy === "compile" ? "Compiling your resume…" : "Compile resume"}</Button>
    </form>

    {error && <p role="alert" className="whitespace-pre-wrap border-l-2 border-bad pl-3 text-sm text-bad">{error}</p>}
    {notice && <p role="status" className="border-l-2 border-accent pl-3 text-sm">{notice}</p>}

    {master?.pdf_url && <section className="space-y-4" aria-label="Resume preview">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule pb-3"><h2 className="text-lg">Your resume</h2><div className="flex flex-wrap gap-5 text-sm"><button type="button" onClick={() => download("pdf")} className="text-accent underline">Download PDF</button><button type="button" onClick={() => download("source")} className="text-accent underline">Download LaTeX</button></div></div>
      <iframe title="Resume PDF preview" src={artifactUrl(master.pdf_url)} className="h-[680px] w-full rounded border border-rule bg-surface" />
      {master.status === "active" ? <p className="text-sm text-good">Current master</p> : <div className="flex flex-wrap items-center gap-4"><Button type="button" disabled={!!busy} onClick={activate}>{busy === "activate" ? "Saving…" : "Use as master"}</Button><p className="text-sm text-ink-secondary">Review the PDF before using it for future tailoring.</p></div>}
    </section>}
  </div>;
}
