"""Exercise the injected scanner against a local DOM, never a live job account."""
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.set_content('''<form id="application">
      <label>First name<input id="first_name" autocomplete="given-name"></label>
      <label>Last name<input id="last_name" autocomplete="family-name"></label>
      <label>Email<input id="email" type="email"></label>
      <label>Phone<input id="phone" value="keep existing"></label>
      <label>Full name<input id="hidden_name" style="display:none"></label>
      <label>Work authorization email<input id="authorization" type="email"></label>
      <label>Referee email<input id="referee" type="email"></label>
      <label>LinkedIn URL<input id="linkedin" type="url"></label>
      <label>Resume<input id="file" type="file"></label>
      <button type="submit">Submit</button>
    </form>''')
    page.evaluate("document.getElementById('application').addEventListener('submit', e => { e.preventDefault(); window.submitted = true; }); document.getElementById('email').addEventListener('input', () => window.changed = true);")
    page.add_script_tag(path=str(Path(__file__).with_name("scanner.js")))
    profile = {"first_name": "Nayan", "last_name": "Kumar", "email": "nayan@example.com", "phone": "+919999999999", "linkedin": "https://linkedin.com/in/example"}
    preview = page.evaluate("p => CareerOSAssistant.collect(p)", profile)
    assert [field["profile_key"] for field in preview] == ["first_name", "last_name", "email", "linkedin"], preview
    selected = [field for field in preview if field["profile_key"] != "last_name"]
    assert page.evaluate("([p,s]) => CareerOSAssistant.fill(p,s)", [profile, selected]) == 3
    assert page.locator("#first_name").input_value() == "Nayan"
    assert page.locator("#last_name").input_value() == ""
    assert page.locator("#phone").input_value() == "keep existing"
    assert page.locator("#authorization").input_value() == ""
    assert page.locator("#referee").input_value() == ""
    assert page.locator("#file").input_value() == ""
    assert page.evaluate("window.changed === true && window.submitted !== true")
    assert page.evaluate("([p,s]) => CareerOSAssistant.fill(p,s)", [profile, selected]) == 0
    browser.close()
    print("Browser passed: preview, explicit selection, framework events, no overwrite, sensitive fields skipped, no upload, no submit")
