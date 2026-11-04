# CareerOS Application Assistant

Local Chrome/Edge Manifest V3 extension. Start CareerOS's backend on `http://127.0.0.1:8010`, then open `http://127.0.0.1:3000/autofill`.

1. Save your explicit application profile in CareerOS.
2. Open `chrome://extensions` or `edge://extensions`, enable Developer mode, choose **Load unpacked**, and select this `extension` folder.
3. Generate a pairing code on CareerOS's Autofill page. Paste it into the extension popup. The code expires after five minutes and is consumed once.
4. Open an application web page and click **Preview empty fields**. Review the values and uncheck any unwanted fields. Click **Fill selected fields**.
5. Review the complete application and submit it yourself. The extension does not click submit, answer eligibility/private questions, bypass a CAPTCHA, or upload files.

Permissions: `activeTab`, `scripting`, `storage`, and only the local API host `http://127.0.0.1:8010/*`. There are no background content scripts and no broad job-board host permissions. Clicking Preview/Fill or reading a job explicitly grants access to the current tab. Revoking access on CareerOS's Autofill page disables future API requests; disconnect removes the token from this browser's local extension storage. Tokens are never synced or put in URLs; the server stores only their hash, bound to the extension that paired. Switching workspaces invalidates old browser credentials.

Supported forms: visible, empty, editable HTML text/email/phone/URL inputs with explicit recognizable labels or autocomplete attributes, including basic Greenhouse/Lever fields. Existing values, custom widgets, file inputs, cross-origin frames, multi-step controls, consent/eligibility/demographic questions, and unfamiliar fields remain manual. Split first/last names must be supplied explicitly in your CareerOS profile.

**Save a job:** on any permitted job page, select the JD text (or use supported Greenhouse/Lever page content), open the popup, and click **Read selected text / job details**. Review/edit title, company, location, URL, and description before saving. Mark the full-description checkbox only when you supplied the complete JD. CareerOS stores that reviewed text; the extension does not crawl or bulk scrape sites.

**Resume:** load prepared PDFs, choose the matching run, and download it. Select the file manually in the website's upload control. Only ready, owned, validated tailoring runs are downloadable through the extension.

Run pure field-classification tests from this directory: `node --test scanner.test.cjs`. An API restart is needed after installing backend updates. If you change the backend port, update the extension's `host_permissions` and `BASE` together, then reload the extension; the shipped package targets 8010.
