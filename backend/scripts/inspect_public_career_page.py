"""Developer research on fixed public pages, not an application collector."""
import json
import requests
from bs4 import BeautifulSoup

for url in ("https://cutshort.io/jobs/software-engineer-jobs", "https://careers.cognizant.com/india-en/jobs/"):
    try:
        response = requests.get(url, timeout=15, headers={"User-Agent": "CareerOS-OSS-Collector/1.0"})
        soup = BeautifulSoup(response.text[:2_000_000], "html.parser")
        print(json.dumps({"url": url, "status": response.status_code, "final": response.url,
            "size": len(response.content), "title": soup.title.get_text() if soup.title else None,
            "headings": [(node.name, node.get("class")) for node in soup.select("h1,h2,h3")][:12],
            "job_links": [node.get("href") for node in soup.select("a[href*='/job/'],a[href*='/jobs/']")][:10],
            "inputs": [{key: node.get(key) for key in ("name", "id", "placeholder", "type")} for node in soup.select("input")][:15],
            "scripts": [(node.get("src") or "").split("?", 1)[0] for node in soup.select("script[src]")][:15]}), flush=True)
    except Exception as exc: print(json.dumps({"url": url, "error": type(exc).__name__}), flush=True)
