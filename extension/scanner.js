/* Runs only after the user clicks Preview/Fill. No background content scripts. */
(function (root) {
  "use strict";
  const forbidden = /password|passcode|captcha|social.security|national.id|passport|aadhar|aadhaar|pan.card|date.of.birth|birthdate|gender|sex\b|race|ethnic|religio|veteran|disab|demograph|pronoun|citizen|nationality|visa|sponsor|authoriz|right.to.work|eligib|salary|compensation|expected.pay|notice.period|consent|agree|signature|legal|cover.letter|address.line|street.address|reference|referee|emergency|parent|guardian|spouse|country.code/i;
  function classify(field) {
    const text = [field.label, field.name, field.id, field.placeholder, field.autocomplete].filter(Boolean).join(" ").replace(/[_-]/g, " ").trim();
    if (forbidden.test(text)) return null;
    const autocomplete = (field.autocomplete || "").toLowerCase().split(/\s+/).pop();
    const known = {"given-name": "first_name", "family-name": "last_name", name: "full_name", email: "email", tel: "phone", "address-level2": "location"};
    if (known[autocomplete]) return known[autocomplete];
    if (/\bfirst name\b|\bgiven name\b/i.test(text)) return "first_name";
    if (/\blast name\b|\bfamily name\b|\bsurname\b/i.test(text)) return "last_name";
    if (/\blinked\s?in\b/i.test(text)) return "linkedin";
    if (/\bgithub\b/i.test(text)) return "github";
    if (/\bportfolio\b|\bpersonal website\b/i.test(text)) return "portfolio";
    if (/\be\s?mail\b/i.test(text) || field.type === "email") return "email";
    if (/\bphone\b|\bmobile\b|\btelephone\b/i.test(text) || field.type === "tel") return "phone";
    if (/\bfull name\b|\byour name\b/i.test(text) || /^(name\s*)+$/i.test(text)) return "full_name";
    if (/\bcurrent location\b|\bcity\b|^location(?:\s+location)*$/i.test(text)) return "location";
    return null;
  }
  function permitted(field) {
    return ["text", "email", "tel", "url", ""].includes((field.type || "text").toLowerCase()) && !field.disabled && !field.readOnly && field.visible && !String(field.value || "").trim();
  }
  function describe(input, index) {
    return { key: String(index), type: input.type, label: [input.getAttribute("aria-label"), ...(input.labels || [])].filter(Boolean).map(item => typeof item === "string" ? item : item.textContent).filter(Boolean).join(" ").trim().slice(0, 250), name: input.name, id: input.id, placeholder: input.placeholder, autocomplete: input.autocomplete, value: input.value, disabled: input.disabled, readOnly: input.readOnly, visible: !!(input.getClientRects().length && getComputedStyle(input).visibility !== "hidden") };
  }
  function collect(profile) {
    return [...document.querySelectorAll("input")].map(describe).filter(permitted).map(field => ({...field, profile_key: classify(field)})).filter(field => field.profile_key && String(profile[field.profile_key] || "").trim()).map(field => ({ key: field.key, profile_key: field.profile_key, label: field.label || field.name || field.id || field.profile_key, value: profile[field.profile_key] }));
  }
  function fill(profile, selected) {
    const fields = collect(profile);
    const inputs = [...document.querySelectorAll("input")];
    let count = 0;
    for (const field of fields) {
      if (!selected.some(choice => choice.key === field.key && choice.profile_key === field.profile_key && choice.label === field.label)) continue;
      const input = inputs[Number(field.key)];
      if (!input || input.value.trim()) continue;
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
      setter.call(input, field.value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      count++;
    }
    return count;
  }
  function jobDraft() {
    const selected = window.getSelection()?.toString().trim() || "";
    const known = document.querySelector("#job_description, #content .content, .posting-page .section-wrapper, .posting-page .content, [data-qa='job-description']");
    return { title: document.querySelector("h1")?.innerText?.trim().slice(0, 200) || "", company: document.querySelector('meta[property="og:site_name"]')?.content || "", location: "", apply_url: location.href, description: (selected || known?.innerText || "").slice(0, 100000) };
  }
  const api = { classify, permitted, collect, fill, jobDraft };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CareerOSAssistant = api;
})(globalThis);
