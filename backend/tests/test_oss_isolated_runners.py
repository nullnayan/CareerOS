from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap


ROOT = Path(__file__).resolve().parents[2]
RUNNERS = ROOT / "backend" / "jobs" / "oss" / "runners"
BACKEND = ROOT / "backend"
ENVS = ROOT / "oss-tools" / "runtime" / "environments"


def isolated_env(**overrides):
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "COMSPEC") if os.environ.get(key)}
    env["PATH"] = os.environ.get("PATH", "")
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update({key: str(value) for key, value in overrides.items()})
    return env


def run_python(python: Path, code: str, *, env=None, timeout=30):
    try:
        result = subprocess.run([str(python), "-c", code], cwd=ROOT, env=env or isolated_env(),
                                capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        raise AssertionError(f"isolated fixture timed out; stderr={error.stderr!r}; stdout={error.stdout!r}") from None
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout)


def test_jobspy_serialization_and_country_limits_run_in_pinned_environment():
    py = ROOT / "backend" / ".source-tools-venv" / "Scripts" / "python.exe"
    code = textwrap.dedent(f"""
        import datetime, json, math, sys
        sys.path.insert(0, {str(RUNNERS)!r})
        import pandas as pd
        import jobspy_runner as r
        values = {{"nan": r._json_value(float('nan')), "pd_na": r._json_value(pd.NA),
                  "nat": r._json_value(pd.NaT), "dt": r._json_value(datetime.date(2026,11,3)),
                  "bdjobs_country": r._country('bdjobs','BD')}}
        try: r._country('naukri','US')
        except r.RunnerFailure as e: values['naukri_us'] = e.reason
        print(json.dumps(values))
    """)
    result = run_python(py, code)
    assert result == {"nan": None, "pd_na": None, "nat": None,
                      "dt": "2026-11-03", "bdjobs_country": "india", "naukri_us": "unsupported"}


def test_jobspy_http_boundary_blocks_redirects_proxies_private_dns_and_external_hosts():
    py = ROOT / "backend" / ".source-tools-venv" / "Scripts" / "python.exe"
    code = textwrap.dedent(f"""
        import json, sys
        from types import SimpleNamespace
        sys.path.insert(0, {str(RUNNERS)!r})
        import jobspy_runner as r
        from requests import Session
        from curl_cffi import requests as curl_requests
        captured = []
        def fake(self, method, url, *args, **kwargs):
            captured.append((url, kwargs.copy()))
            return SimpleNamespace(url=url, close=lambda: None)
        Session.request = fake
        curl_requests.Session.request = fake
        r.socket.getaddrinfo = lambda *a, **k: [(2,1,6,'',('8.8.8.8',443))]
        budget, originals = r._guard_network('naukri','india')
        session = Session()
        session.request('GET','https://www.naukri.com/jobs')
        external = False
        try: session.request('GET','https://rapidapi.com/jobs')
        except RuntimeError: external = True
        r.socket.getaddrinfo = lambda *a, **k: [(2,1,6,'',('10.0.0.1',443))]
        private = False
        try: session.request('GET','https://www.naukri.com/private')
        except RuntimeError: private = True
        for cls, original in originals: cls.request = original
        print(json.dumps({{'redirects': captured[0][1].get('allow_redirects'),
                          'timeout': captured[0][1].get('timeout'), 'external_blocked': external,
                          'private_dns_blocked': private, 'count': budget['count']}}))
    """)
    result = run_python(py, code)
    assert result["redirects"] is False
    assert result["timeout"] <= 15
    assert result["external_blocked"] is True
    assert result["private_dns_blocked"] is True
    assert result["count"] == 1


def test_ats_resolution_and_dns_boundary_run_in_dedicated_environment():
    py = ENVS / "ats" / "Scripts" / "python.exe"
    code = textwrap.dedent(f"""
        import json, sys
        sys.path.insert(0, {str(RUNNERS)!r})
        import ats_runner as runner
        from ats_scrapers import resolve_careers_url
        runner.socket.getaddrinfo = lambda *a, **k: [(2,1,6,'',('8.8.8.8',443))]
        allowed = runner._host_allowed('https://acme.myworkdayjobs.com/en-US/careers',('myworkdayjobs.com',))
        wrong_host = runner._host_allowed('https://evil.example/careers',('myworkdayjobs.com',))
        runner.socket.getaddrinfo = lambda *a, **k: [(2,1,6,'',('192.168.1.5',443))]
        private_dns = runner._host_allowed('https://acme.myworkdayjobs.com/en-US/careers',('myworkdayjobs.com',))
        stripe = resolve_careers_url('https://job-boards.greenhouse.io/stripe')
        tcs = resolve_careers_url('https://www.tcs.com/careers/india')
        print(json.dumps({{'allowed':allowed,'wrong_host':wrong_host,'private_dns':private_dns,
                          'stripe_ats':stripe.ats.value if stripe else None,'tcs_mapped':bool(tcs)}}))
    """)
    result = run_python(py, code)
    assert result == {"allowed": True, "wrong_host": False, "private_dns": False,
                      "stripe_ats": "greenhouse", "tcs_mapped": False}


def test_crawl4ai_deterministic_html_extraction_and_next_page_boundary():
    py = ENVS / "crawl4ai" / "Scripts" / "python.exe"
    html = """<html><body><article class='job-card'><a href='/job/17'><h2 class='title'>Software Engineer</h2></a><span class='company'>Example Co</span><span class='location'>Bengaluru</span><div class='description'>Build reliable data services.</div></article><a rel='next' href='/jobs?page=2'>Next</a></body></html>"""
    code = textwrap.dedent(f"""
        import json, sys
        sys.path.insert(0, {str(RUNNERS)!r})
        sys.path.insert(0, {str(BACKEND)!r})
        import crawl4ai_runner as r
        profile = {{'job_link_selectors':[\"a[href*='/job/']\"], 'title_selectors':['.title'],
                   'company_selectors':['.company'], 'location_selectors':['.location'],
                   'description_selectors':['.description'], 'next_selectors':[\"a[rel='next']\"],
                   'challenge_indicators':['captcha'], 'login_indicators':['sign in']}}
        records, text, next_links = r._extract_page({html!r}, 'https://cutshort.io/jobs', profile, ['cutshort.io'])
        print(json.dumps({{'records':records,'text':text,'next_links':next_links,
                          'reject_http':not r._domain_allowed('http://cutshort.io/jobs',['cutshort.io']),
                          'reject_external':not r._domain_allowed('https://evil.example/jobs',['cutshort.io'])}}))
    """)
    result = run_python(py, code, env=isolated_env(
        CRAWL4_AI_BASE_DIRECTORY=ROOT / "oss-tools" / "runtime" / "crawl-data",
        USERPROFILE=ROOT / "oss-tools" / "runtime" / "homes" / "test",
        HOME=ROOT / "oss-tools" / "runtime" / "homes" / "test"), timeout=8)
    assert len(result["records"]) == 1
    assert result["records"][0]["title"] == "Software Engineer"
    assert result["records"][0]["company"] == "Example Co"
    assert result["records"][0]["description_complete"] is False
    assert result["next_links"] == ["https://cutshort.io/jobs?page=2"]
    assert result["reject_http"] is True and result["reject_external"] is True


def test_crawl_runner_traverses_one_page_resumes_and_fetches_only_bounded_details():
    py = ENVS / "crawl4ai" / "Scripts" / "python.exe"
    code = textwrap.dedent(f"""
        import json, sys, types
        sys.path.insert(0, {str(RUNNERS)!r})
        sys.path.insert(0, {str(BACKEND)!r})
        import crawl4ai_runner as r
        r._public_dns = lambda host: True
        class CacheMode: BYPASS = 'bypass'
        class Config:
            def __init__(self, **kwargs): self.kwargs=kwargs
        robots = 'User-agent: *\\nAllow: /'
        listing = '''<html><body><script type="application/ld+json">{{"@context":"https://schema.org","@type":"JobPosting","identifier":"cut-17","title":"Software Engineer","hiringOrganization":{{"name":"Example"}},"jobLocation":{{"address":{{"addressLocality":"Bengaluru"}}}},"url":"https://cutshort.io/jobs/17","description":"A short list excerpt."}}</script><a rel="next" href="/jobs?page=2">Next</a></body></html>'''
        detail = '''<html><body><script type="application/ld+json">{{"@type":"JobPosting","identifier":"cut-17","title":"Software Engineer","hiringOrganization":{{"name":"Example"}},"url":"https://cutshort.io/jobs/17","description":"Detailed responsibilities for the software engineer role."}}</script><div class="description">Detailed responsibilities for the software engineer role.</div></body></html>'''
        calls=[]
        class Result:
            success=True; status_code=200; redirected_url=None
            def __init__(self,url,html): self.url=url; self.html=html; self.cleaned_html=html
        class Strategy:
            def set_hook(self,*args): pass
        class Crawler:
            crawler_strategy=Strategy()
            def __init__(self,**kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            async def arun(self,url,config=None):
                calls.append(url)
                if url.endswith('/robots.txt'): return Result(url,robots)
                if url.endswith('/jobs/17'): return Result(url,detail)
                return Result(url,listing)
        fake=types.ModuleType('crawl4ai')
        fake.AsyncWebCrawler=Crawler; fake.BrowserConfig=Config; fake.CrawlerRunConfig=Config; fake.CacheMode=CacheMode
        sys.modules['crawl4ai']=fake
        request={{'source_id':'cutshort','entry_url':'https://cutshort.io/jobs','role':'software engineer',
                 'location':'Bengaluru','cursor':None,'deadline_seconds':45,'max_results':1,'max_details':1}}
        result=r.run(request)
        print(json.dumps({{'batch':result,'calls':calls}}))
    """)
    result = run_python(py, code, env=isolated_env(
        CRAWL4_AI_BASE_DIRECTORY=ROOT / "oss-tools" / "runtime" / "crawl-data",
        USERPROFILE=ROOT / "oss-tools" / "runtime" / "homes" / "test",
        HOME=ROOT / "oss-tools" / "runtime" / "homes" / "test"), timeout=30)
    assert result["batch"]["coverage"] == "partial"
    assert result["batch"]["next_url"] == "https://cutshort.io/jobs?page=2"
    assert result["batch"]["jobs"][0]["description_complete"] is True
    assert result["batch"]["description_pages"] == 1
    assert len(result["calls"]) == 3


def test_ats_snapshot_reuses_catalogue_and_expiry_restarts_safely():
    py = ENVS / "ats" / "Scripts" / "python.exe"
    code = textwrap.dedent(f"""
        import json, sys, tempfile, base64, os
        from pathlib import Path
        from types import SimpleNamespace
        sys.path.insert(0, {str(RUNNERS)!r})
        import ats_runner as r
        from ats_scrapers.models import Job
        calls=[]
        async def afetch():
            calls.append(1)
            return [Job(url=f'https://job-boards.greenhouse.io/fixture/jobs/{{i}}', title='Engineer', company='Fixture', ats_type='greenhouse', ats_id=str(i), location='India') for i in range(3)]
        request={{'entry_url':'https://job-boards.greenhouse.io/fixture','query_fingerprint':'fixture', 'role':'engineer','location':'India', 'cursor':None,'tool':'ats_scrapers','source_id':'fixture'}}
        with tempfile.TemporaryDirectory() as tmp:
            r.__file__=str(Path(tmp)/'backend/jobs/oss/runners/ats_runner.py')
            jobs, offset, version, cached=r._snapshot_jobs(request,SimpleNamespace(afetch=afetch))
            state={{'v':1,'tool':'ats_scrapers','source_id':'fixture','query_fingerprint':'fixture','state':{{'offset':1,'snapshot':version}}}}
            request['cursor']=base64.urlsafe_b64encode(json.dumps(state).encode()).decode().rstrip('=')
            again, offset2, version2, cached2=r._snapshot_jobs(request,SimpleNamespace(afetch=afetch))
            assert len(calls)==1 and cached2 and offset2==1 and len(again)==3 and version2==version
            for path in (Path(tmp)/'oss-tools/runtime/ats-snapshots').glob('*.json'): os.utime(path,(1,1))
            _, reset, _, _=r._snapshot_jobs(request,SimpleNamespace(afetch=afetch))
            assert len(calls)==2 and reset==0
        print(json.dumps({{'ok':True}}))
    """)
    assert run_python(py, code)["ok"]
