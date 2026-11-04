"""Real unpacked popup QA using a disposable DB and a localhost-only form.

The copied test manifest adds only the fixture host so headless Chromium can
exercise injection without a physical toolbar click granting activeTab.
The shipped manifest is never changed.
"""
from pathlib import Path
import json
import shutil
import sys
import tempfile
import threading
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import uvicorn
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from playwright.sync_api import sync_playwright, expect
from db.models import Base
from db.session import get_db
from main import app


def main():
    with tempfile.TemporaryDirectory(prefix="careeros-extension-qa-") as temporary:
        root = Path(temporary)
        extension = root / "extension"
        shutil.copytree(Path(__file__).parent, extension, ignore=shutil.ignore_patterns("__pycache__", "*.zip"))
        manifest_path = extension / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["host_permissions"].append("http://127.0.0.1:8011/*")
        manifest_path.write_text(json.dumps(manifest))
        engine = create_engine("sqlite:///" + str(root / "qa.sqlite"), connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine)
        def database():
            with factory() as db: yield db
        app.dependency_overrides[get_db] = database
        client = TestClient(app)
        client.put("/autofill/profile", json={"first_name": "Nayan", "email": "nayan@example.com"})
        code = client.post("/autofill/pairings", json={}).json()["code"]
        @app.get("/extension-qa-fixture", response_class=HTMLResponse)
        def fixture():
            return '<h1>Graduate Engineer</h1><label>First name<input id="first_name"></label><label>Email<input id="email" type="email"></label><label>Work authorization<input id="auth"></label><button type="submit">Submit</button>'
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8011, lifespan="off", log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True); thread.start()
        for _ in range(100):
            if server.started: break
            time.sleep(.1)
        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(str(root / "browser"), channel="chromium", headless=True, ignore_default_args=["--disable-extensions"], args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"])
                context.route("http://127.0.0.1:8010/**", lambda route: route.continue_(url=route.request.url.replace(":8010", ":8011")))
                inventory = context.new_page(); inventory.goto("chrome://extensions")
                item = inventory.locator("extensions-item").first
                item.wait_for(timeout=15000)
                extension_id = item.get_attribute("id")
                assert extension_id and len(extension_id) == 32, extension_id
                application = context.new_page(); application.goto("http://127.0.0.1:8011/extension-qa-fixture")
                popup = context.new_page(); popup.goto(f"chrome-extension://{extension_id}/popup.html")
                errors = []; popup.on("pageerror", lambda error: errors.append(str(error)))
                popup.get_by_label("Pairing code").fill(code)
                popup.get_by_role("button", name="Pair extension", exact=True).click()
                popup.get_by_text("Connected locally", exact=True).wait_for()
                # Physical action-toolbar invocation supplies activeTab in normal
                # use; this headless harness supplies only its own fixture tab.
                popup.evaluate("""async () => {
                    const tabs = await chrome.tabs.query({url:'http://127.0.0.1:8011/extension-qa-fixture'});
                    if (!tabs.length) throw new Error('QA fixture tab missing');
                    chrome.tabs.query = async () => [tabs[0]];
                }""")
                popup.get_by_role("button", name="Preview empty fields", exact=True).click()
                try:
                    popup.get_by_text("Review the values, select fields", exact=False).wait_for()
                except Exception:
                    print("Popup preview status:", popup.locator("#status").inner_text(), flush=True)
                    raise
                expect(popup.locator("#fields input:checked")).to_have_count(2)
                popup.get_by_role("button", name="Fill selected fields", exact=True).click()
                popup.get_by_text("Filled 2 fields.", exact=False).wait_for()
                assert application.locator("#first_name").input_value() == "Nayan"
                assert application.locator("#email").input_value() == "nayan@example.com"
                assert application.locator("#auth").input_value() == ""
                credential = client.get("/autofill/credentials").json()[0]
                client.delete("/autofill/credentials/" + credential["id"])
                popup.get_by_role("button", name="Preview empty fields", exact=True).click()
                popup.get_by_text("Extension access was revoked", exact=False).wait_for()
                assert not errors, errors
                context.close()
                print("Unpacked MV3 passed: actual popup, extension-origin pairing, authenticated profile preview, selected empty-input fill, sensitive-input skip, and revocation")
        finally:
            server.should_exit = True; thread.join(timeout=10)
            app.dependency_overrides.clear(); engine.dispose()


if __name__ == "__main__": main()
