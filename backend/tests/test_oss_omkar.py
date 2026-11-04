from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from jobs.oss.contracts import FailureReason


RUNNER_DIR = Path(__file__).resolve().parents[1] / "jobs" / "oss" / "runners"
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))
import omkar_runner


def test_each_local_project_pagination_shape_is_checked(monkeypatch):
    instahyre = ModuleType("instahyre")
    instahyre.jobs = SimpleNamespace(search=lambda **_: {"jobs": [{"id": 1}], "pagination": {"total_pages": 3}})
    monkeypatch.setitem(sys.modules, "instahyre", instahyre)
    result = omkar_runner._page({"source_id": "instahyre", "role": "engineer", "location": "Bengaluru"}, 1)
    assert result == {"jobs": [{"id": 1}], "has_more": True, "next_page": 2}

    internshala = ModuleType("internshala")
    internshala.listings = SimpleNamespace(jobs=lambda **_: {"jobs": [{"id": 2}], "pagination": {"is_last_page": False}},
                                            internships=lambda **_: {"internships": [{"id": 3}], "pagination": {"is_last_page": True}})
    monkeypatch.setitem(sys.modules, "internshala", internshala)
    jobs = omkar_runner._page({"source_id": "internshala_jobs", "country_code": "IN",
                               "role": "engineer", "location": "Bengaluru"}, 4)
    internships = omkar_runner._page({"source_id": "internshala_internships", "country_code": "IN",
                                      "role": "engineer", "location": "Bengaluru"}, 1)
    assert jobs["next_page"] == 5 and jobs["has_more"] is True
    assert internships["jobs"] == [{"id": 3}] and internships["has_more"] is False

    shine = ModuleType("shine")
    shine.jobs = SimpleNamespace(search=lambda **_: {"jobs": [{"id": 4}], "pagination": {"total_pages": 2}})
    monkeypatch.setitem(sys.modules, "shine", shine)
    result = omkar_runner._page({"source_id": "shine", "role": "engineer", "location": "Bengaluru"}, 1)
    assert result["jobs"] == [{"id": 4}] and result["next_page"] == 2


def test_details_use_local_project_functions_and_expected_references(monkeypatch):
    instahyre = ModuleType("instahyre")
    instahyre.jobs = SimpleNamespace(details=lambda *args, **kwargs: {"description": "Instahyre full description"})
    monkeypatch.setitem(sys.modules, "instahyre", instahyre)
    assert omkar_runner._detail({"source_id": "instahyre"}, {"id": 10})["description"].startswith("Instahyre")

    internshala = ModuleType("internshala")
    internshala.details = SimpleNamespace(internship=lambda ref: {"description": ref["slug"]},
                                         job=lambda ref: {"description": ref["slug"]})
    monkeypatch.setitem(sys.modules, "internshala", internshala)
    detail = omkar_runner._detail({"source_id": "internshala_internships"},
                                  {"link": "https://internshala.com/internship/detail/data-intern"})
    assert detail == {"description": "data-intern"}

    shine = ModuleType("shine")
    shine.jobs = SimpleNamespace(details=lambda job_id: {"description_html": f"Details {job_id}"})
    monkeypatch.setitem(sys.modules, "shine", shine)
    assert omkar_runner._detail({"source_id": "shine"}, {"id": 12})["description_html"] == "Details 12"


def test_normalization_discards_recruiter_personal_fields_and_keeps_stipend_period():
    row = omkar_runner._clean({"id": 3, "link": "https://internshala.com/internship/detail/abc",
                               "email": "recruiter@example.com", "phone": "555-0100",
                               "recruiter_name": "Person", "stipend": {"amount": 15000, "period": "monthly"}},
                              "internshala_internships")
    assert row["source_url"] == row["apply_url"]
    assert row["salary"]["period"] == "monthly"
    assert row["employment_type"] == "internship"
    assert not {"email", "phone", "recruiter_name"} & row.keys()


@pytest.mark.parametrize("tool,source,reason", [
    ("internshala", "internshala_jobs", FailureReason.BLOCKED),
])
def test_upstream_access_gates_stop_before_any_source_call(tool, source, reason):
    with pytest.raises(omkar_runner.RunnerFailure) as error:
        omkar_runner.run({"tool": tool, "source_id": source})
    assert error.value.reason == reason.value


def test_instahyre_maps_country_and_generic_title_without_an_exact_skill(monkeypatch):
    captured = {}
    def search(**kwargs):
        captured.update(kwargs)
        return {"jobs": [], "pagination": {"total_pages": 0}}
    fake = ModuleType("instahyre")
    fake.jobs = SimpleNamespace(search=search)
    monkeypatch.setitem(sys.modules, "instahyre", fake)
    result = omkar_runner._page({"source_id": "instahyre", "role": "Software Engineer", "location": "India"}, 1)
    assert captured["query"] is None and captured["location"] is None
    assert result["has_more"] is False


def test_shine_detail_requests_stay_inside_the_same_network_guard(monkeypatch):
    from types import SimpleNamespace

    class Session:
        request = None

    request_count = {"value": 0}

    def original_request(self, method, url, *args, **kwargs):
        return SimpleNamespace(url=url, close=lambda: None)

    def guarded_request(self, method, url, *args, **kwargs):
        request_count["value"] += 1
        return original_request(self, method, url, *args, **kwargs)

    Session.request = original_request
    fake_requests = SimpleNamespace(Session=Session)
    monkeypatch.setitem(sys.modules, "curl_cffi", SimpleNamespace(requests=fake_requests))
    fake_fetch = SimpleNamespace()
    fake_shine = ModuleType("shine")
    fake_shine.jobs = SimpleNamespace()
    fake_shine.fetch = fake_fetch
    monkeypatch.setitem(sys.modules, "shine", fake_shine)
    fake_config = ModuleType("config")
    monkeypatch.setitem(sys.modules, "config", fake_config)
    budget = {"count": 0, "exceeded": False, "outside": False}

    def start_guard():
        Session.request = guarded_request
        return budget, original_request

    def fake_page(request, page):
        assert Session.request is guarded_request
        Session().request("GET", "https://www.shine.com/jobs")
        budget["count"] += 1
        return {"jobs": [{"id": 7, "title": "Engineer", "company": "Example",
                           "link": "https://www.shine.com/jobs/7"}], "has_more": False,
                "next_page": None}

    def fake_detail(request, row):
        assert Session.request is guarded_request
        Session().request("GET", "https://www.shine.com/jobs/7")
        budget["count"] += 1
        return {"description": "Detailed responsibilities for the engineering role."}

    monkeypatch.setattr(omkar_runner, "_guard_shine_requests", start_guard)
    monkeypatch.setattr(omkar_runner, "_page", fake_page)
    monkeypatch.setattr(omkar_runner, "_detail", fake_detail)
    payload = {"tool": "shine", "source_id": "shine", "role": "engineer",
               "location": "Bengaluru", "country_code": "IN", "cursor": None,
               "query_fingerprint": "f" * 64, "max_results": 1, "max_details": 1}
    result = omkar_runner.run(payload)
    assert request_count["value"] == 2
    assert result["request_count"] == 2
    assert result["jobs"][0]["description_complete"] is True
    assert Session.request is original_request
