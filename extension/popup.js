"use strict";
const BASE = "http://127.0.0.1:8010/autofill";
const $ = id => document.getElementById(id);
let token = "", profile = {}, preview = [], previewTab = null;
function status(message) { $("status").textContent = message; }
async function request(path, method = "GET", body) {
  const response = await fetch(BASE + path, { method, headers: { "X-CareerOS-Extension": chrome.runtime.id, ...(token ? { Authorization: "Bearer " + token } : {}), ...(body ? { "Content-Type": "application/json" } : {}) }, body: body ? JSON.stringify(body) : undefined });
  if (!response.ok) {
    let detail = "Request failed";
    try { const data = await response.json(); detail = typeof data.detail === "string" ? data.detail : "Check the supplied fields."; } catch (_) {}
    throw new Error(detail);
  }
  return response;
}
function guarded(action) { return async event => { try { await action(event); } catch (error) { status(error.message || "CareerOS could not be reached. Start the local backend."); } }; }
async function tab() {
  const [active] = await chrome.tabs.query({active: true, currentWindow: true});
  if (!active?.id || !/^https?:\/\//.test(active.url || "")) throw new Error("Open a job or application web page first.");
  return active;
}
async function inspect(active, operation, ...args) {
  await chrome.scripting.executeScript({target: {tabId: active.id}, files: ["scanner.js"]});
  const results = await chrome.scripting.executeScript({target: {tabId: active.id}, func: (operation, args) => globalThis.CareerOSAssistant[operation](...args), args: [operation, args]});
  return results[0]?.result;
}
async function connect() {
  token = (await chrome.storage.local.get("careerosToken")).careerosToken || "";
  $("connected").hidden = !token; $("pairing").hidden = !!token;
}
$("pair").addEventListener("click", guarded(async () => {
  const response = await request("/pair", "POST", {code: $("code").value.trim(), label: "CareerOS browser extension"});
  const data = await response.json();
  await chrome.storage.local.set({careerosToken: data.token}); $("code").value = "";
  await connect(); status("Paired. Preview fields on your application page.");
}));
$("disconnect").addEventListener("click", guarded(async () => {
  await chrome.storage.local.remove("careerosToken"); await connect();
  profile = {}; preview = []; $("fields").replaceChildren(); $("fill").disabled = true;
  status("Disconnected from this browser. Revoke the credential in CareerOS if you no longer use it.");
}));
$("preview").addEventListener("click", guarded(async () => {
  profile = await (await request("/extension/profile")).json();
  const active = await tab(); previewTab = {id: active.id, url: active.url};
  preview = await inspect(active, "collect", profile);
  $("fields").replaceChildren();
  for (const field of preview) {
    const label = document.createElement("label"); label.className = "check";
    const input = document.createElement("input"); input.type = "checkbox"; input.checked = true; input.dataset.key = field.key;
    const text = document.createElement("span"); text.textContent = field.label;
    const value = document.createElement("span"); value.className = "value"; value.textContent = field.value;
    text.append(value); label.append(input, text); $("fields").append(label);
  }
  $("fill").disabled = !preview.length;
  status(preview.length ? "Review the values, select fields, then click Fill." : "No supported empty inputs found. Fill your profile in CareerOS, or complete this form manually.");
}));
$("fill").addEventListener("click", guarded(async () => {
  const active = await tab();
  if (!previewTab || previewTab.id !== active.id || previewTab.url !== active.url) throw new Error("The page changed. Preview fields again.");
  // Recheck authorization immediately before using cached profile values.
  const fresh = await (await request("/extension/profile")).json();
  if (JSON.stringify(fresh) !== JSON.stringify(profile)) throw new Error("Your profile changed. Preview fields again.");
  const keys = [...$("fields").querySelectorAll("input:checked")].map(input => input.dataset.key);
  const selected = preview.filter(field => keys.includes(field.key));
  const count = await inspect(active, "fill", profile, selected);
  $("fill").disabled = true; status(`Filled ${count} fields. Review the application before submitting it yourself.`);
}));
$("draft").addEventListener("click", guarded(async () => {
  const draft = await inspect(await tab(), "jobDraft");
  for (const [key, value] of Object.entries(draft)) $("job").elements.namedItem(key).value = value;
  $("job").elements.namedItem("complete").checked = false;
  status("Review title, company, URL, and description. On other sites select the JD text first, or paste it here.");
}));
$("job").addEventListener("submit", guarded(async event => {
  event.preventDefault(); const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries([...form.entries()].filter(([key]) => key !== "complete"));
  payload.description_complete = form.get("complete") === "on";
  await request("/extension/import", "POST", payload);
  status("Saved in CareerOS Jobs. Open the site to review eligibility and prepare your resume.");
}));
$("resumes").addEventListener("click", guarded(async () => {
  const resumes = await (await request("/extension/resumes")).json();
  $("resume").replaceChildren(new Option("Choose a prepared resume", ""));
  for (const resume of resumes) $("resume").append(new Option(resume.label, resume.id));
  $("download").disabled = true; status(resumes.length ? "Choose the resume for this application." : "No prepared PDFs yet. Generate a resume in CareerOS first.");
}));
$("resume").addEventListener("change", () => { $("download").disabled = !$("resume").value; });
$("download").addEventListener("click", guarded(async () => {
  const id = $("resume").value; if (!id) return;
  const response = await request("/extension/resumes/" + encodeURIComponent(id));
  const blob = await response.blob(); const url = URL.createObjectURL(blob);
  const link = document.createElement("a"); link.href = url; link.download = "CareerOS-resume.pdf"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
  status("PDF downloaded. Select it manually in the application’s upload field.");
}));
connect().catch(error => status(error.message));
