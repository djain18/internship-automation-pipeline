import json
from pathlib import Path

import hunter
from hunter import _pick, company_domain, find_company_contact, find_company_contact_with_status

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _payload():
    return json.loads((FIXTURES / "hunter-domain-response.json").read_text(encoding="utf-8"))


def _record(**overrides):
    base = {
        "company": "Fixture Labs",
        "company_url": "https://fixturelabs.example/careers",
        "discovered_at": "2026-09-11",
    }
    base.update(overrides)
    return base


class _MemoryState:
    def __init__(self):
        self.use = {"searches": 0, "verifications": 0}
        self.domains = {}
        self.calls = []

    def hunter_month_use(self, _month):
        return dict(self.use)

    def record_hunter_use(self, _month, kind):
        self.use[kind] += 1

    def hunter_domain_cache(self, _month, domain):
        entry = self.domains.get(domain)
        return dict(entry["result"]) if entry and entry.get("result") else None

    def cache_hunter_domain(self, _month, domain, result):
        self.domains[domain] = {"result": result}


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def _clear_key(monkeypatch):
    monkeypatch.delenv("HUNTER_API_KEY", raising=False)


def test_prefers_founder_over_generic_and_weak() -> None:
    pick = _pick(_payload()["data"]["emails"], 80)
    assert pick["value"] == "aarav@fixturelabs.example"


def test_generic_only_and_low_confidence_are_rejected() -> None:
    emails = _payload()["data"]["emails"]
    assert _pick([emails[1]], 80) is None
    assert _pick([emails[2]], 80) is None


def test_blocked_and_webmail_domains_never_query(monkeypatch) -> None:
    _clear_key(monkeypatch)
    monkeypatch.setenv("HUNTER_API_KEY", "key")
    state = _MemoryState()
    monkeypatch.setattr(
        hunter.requests, "get",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no HTTP for blocked hosts")),
    )
    scoring = {"hunter_enabled": True, "hunter_monthly_max_searches": 25}
    assert find_company_contact(_record(company_url="https://www.linkedin.com/company/x"), scoring, state, "2026-09") is None
    assert find_company_contact(_record(company_url=""), scoring, state, "2026-09") is None
    assert state.use == {"searches": 0, "verifications": 0}


def test_missing_key_and_disabled_flag_skip_quietly(monkeypatch) -> None:
    _clear_key(monkeypatch)
    state = _MemoryState()
    scoring = {"hunter_enabled": True, "hunter_monthly_max_searches": 25}
    assert find_company_contact(_record(), scoring, state, "2026-09") is None
    monkeypatch.setenv("HUNTER_API_KEY", "key")
    assert find_company_contact(_record(), {"hunter_enabled": False}, state, "2026-09") is None


def test_with_status_distinguishes_every_early_return(monkeypatch) -> None:
    """Every early return used to look identical (silent None) from outside
    -- a missing key, a blocked domain, and a real HTTP error were
    indistinguishable, which is how the key never reaching Modal went
    unnoticed. Each miss must carry its own reason."""
    state = _MemoryState()

    _clear_key(monkeypatch)
    contact, status = find_company_contact_with_status(_record(), {"hunter_enabled": True}, state, "2026-09")
    assert (contact, status) == (None, "no_api_key")

    monkeypatch.setenv("HUNTER_API_KEY", "key")
    contact, status = find_company_contact_with_status(_record(), {"hunter_enabled": False}, state, "2026-09")
    assert (contact, status) == (None, "disabled")

    contact, status = find_company_contact_with_status(
        _record(company_url=""), {"hunter_enabled": True}, state, "2026-09"
    )
    assert (contact, status) == (None, "no_domain")

    scoring = {"hunter_enabled": True, "hunter_monthly_max_searches": 0}
    contact, status = find_company_contact_with_status(_record(), scoring, state, "2026-09")
    assert (contact, status) == (None, "cap_reached")


def test_with_status_reports_no_match_and_ok(monkeypatch) -> None:
    state = _MemoryState()
    monkeypatch.setenv("HUNTER_API_KEY", "key")

    def fake_get(url, params=None, timeout=None):
        if url.endswith("/account"):
            return _Response({"data": {"requests": {"searches": {"available": 20}, "verifications": {"available": 0}}}})
        return _Response({"data": {"emails": []}})

    monkeypatch.setattr(hunter.requests, "get", fake_get)
    scoring = {"hunter_enabled": True, "hunter_monthly_max_searches": 25, "hunter_min_confidence": 80}
    contact, status = find_company_contact_with_status(_record(), scoring, state, "2026-09")
    assert (contact, status) == (None, "no_match")

    # A record for a different, cached domain returns ok on a real pick.
    state2 = _MemoryState()

    def fake_get_found(url, params=None, timeout=None):
        if url.endswith("/account"):
            return _Response({"data": {"requests": {"searches": {"available": 20}, "verifications": {"available": 0}}}})
        return _Response(_payload())

    monkeypatch.setattr(hunter.requests, "get", fake_get_found)
    contact, status = find_company_contact_with_status(_record(), scoring, state2, "2026-09")
    assert status == "ok"
    assert contact["email"] == "aarav@fixturelabs.example"

    # A second lookup for the same domain this month hits the cache.
    contact, status = find_company_contact_with_status(_record(), scoring, state2, "2026-09")
    assert status == "cache_hit"


def test_with_status_reports_http_error(monkeypatch) -> None:
    state = _MemoryState()
    monkeypatch.setenv("HUNTER_API_KEY", "key")

    class _FailingResponse:
        status_code = 401

        def raise_for_status(self):
            import requests

            raise requests.HTTPError(response=self)

    monkeypatch.setattr(hunter.requests, "get", lambda *_a, **_k: _FailingResponse())
    scoring = {"hunter_enabled": True, "hunter_monthly_max_searches": 25}
    contact, status = find_company_contact_with_status(_record(), scoring, state, "2026-09")
    assert (contact, status) == (None, "http_error:401")


def test_linkedin_url_from_hunter_result() -> None:
    """Hunter result with LinkedIn URL includes it in contact."""
    from hunter import _contact_from_pick
    pick = {
        "value": "aarav@example.com",
        "first_name": "Aarav",
        "last_name": "Sharma",
        "confidence": 95,
        "type": "personal",
        "position": "Founder",
        "linkedin_url": "https://linkedin.com/in/aarav-sharma",
        "sources": [{"uri": "https://example.com/team"}],
    }
    record = _record()
    contact = _contact_from_pick(pick, record, False, None)
    assert contact["linkedin"] == "https://linkedin.com/in/aarav-sharma"


def test_linkedin_url_never_guessed_from_hunter() -> None:
    """Hunter contact without explicit LinkedIn URL has empty LinkedIn field."""
    from hunter import _contact_from_pick
    pick = {
        "value": "aarav@example.com",
        "first_name": "Aarav",
        "last_name": "Sharma",
        "confidence": 95,
        "type": "personal",
        "position": "Founder",
        "sources": [{"uri": "https://example.com/team"}],
    }
    record = _record()
    contact = _contact_from_pick(pick, record, False, None)
    assert contact["linkedin"] == ""


def test_monthly_cap_and_empty_quota_stop_before_http(monkeypatch) -> None:
    _clear_key(monkeypatch)
    monkeypatch.setenv("HUNTER_API_KEY", "key")
    monkeypatch.setattr(
        hunter.requests, "get",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("capped means no HTTP")),
    )
    state = _MemoryState()
    state.use["searches"] = 25
    scoring = {"hunter_enabled": True, "hunter_monthly_max_searches": 25}
    assert find_company_contact(_record(), scoring, state, "2026-09") is None


def test_finder_result_is_medium_never_verified_by_default(monkeypatch) -> None:
    _clear_key(monkeypatch)
    monkeypatch.setenv("HUNTER_API_KEY", "key")
    state = _MemoryState()
    calls = []

    def fake_get(url, *, params, **_kwargs):
        calls.append(url)
        if url.endswith("/account"):
            return _Response({"data": {"requests": {"searches": {"available": 20}, "verifications": {"available": 0}}}})
        return _Response(_payload())

    monkeypatch.setattr(hunter.requests, "get", fake_get)
    scoring = {
        "hunter_enabled": True, "hunter_verify": False,
        "hunter_min_confidence": 80, "hunter_limit_per_domain": 10,
        "hunter_monthly_max_searches": 25,
    }
    contact = find_company_contact(_record(), scoring, state, "2026-09")
    assert contact["email"] == "aarav@fixturelabs.example"
    assert contact["name"] == "Aarav Sharma"
    assert contact["verification_status"] == "hunter_found_unverified"
    assert contact["verification_status"] not in {"published_by_source", "human_verified"}
    assert contact["confidence"] == "medium"
    assert contact["contact_priority"] == "preferred_named"
    assert contact["source_url"] == "https://fixturelabs.example/team"
    assert not any(url.endswith("/email-verifier") for url in calls)
    assert state.use == {"searches": 1, "verifications": 0}
    calls.clear()
    again = find_company_contact(_record(), scoring, state, "2026-09")
    assert again["email"] == "aarav@fixturelabs.example"
    assert again.get("cache_hit") is True
    assert calls == []
    assert state.use == {"searches": 1, "verifications": 0}


def test_verified_deliverable_earns_high_confidence(monkeypatch) -> None:
    _clear_key(monkeypatch)
    monkeypatch.setenv("HUNTER_API_KEY", "key")
    state = _MemoryState()

    def fake_get(url, *, params, **_kwargs):
        if url.endswith("/account"):
            return _Response({"data": {"requests": {"searches": {"available": 20}, "verifications": {"available": 10}}}})
        if url.endswith("/email-verifier"):
            return _Response({"data": {"status": "valid", "result": "deliverable", "score": 95}})
        return _Response(_payload())

    monkeypatch.setattr(hunter.requests, "get", fake_get)
    scoring = {
        "hunter_enabled": True, "hunter_verify": True,
        "hunter_min_confidence": 80, "hunter_limit_per_domain": 10,
        "hunter_monthly_max_searches": 25, "hunter_monthly_max_verifications": 10,
    }
    contact = find_company_contact(_record(), scoring, state, "2026-09")
    assert contact["verification_status"] == "hunter_verified_deliverable"
    assert contact["confidence"] == "high"
    assert state.use == {"searches": 1, "verifications": 1}


def test_accept_all_caps_confidence_at_medium(monkeypatch) -> None:
    _clear_key(monkeypatch)
    monkeypatch.setenv("HUNTER_API_KEY", "key")
    state = _MemoryState()
    payload = _payload()
    payload["data"]["accept_all"] = True

    def fake_get(url, *, params, **_kwargs):
        if url.endswith("/account"):
            return _Response({"data": {"requests": {"searches": {"available": 20}, "verifications": {"available": 10}}}})
        if url.endswith("/email-verifier"):
            return _Response({"data": {"status": "valid", "result": "deliverable", "score": 95}})
        return _Response(payload)

    monkeypatch.setattr(hunter.requests, "get", fake_get)
    scoring = {
        "hunter_enabled": True, "hunter_verify": True,
        "hunter_min_confidence": 80, "hunter_limit_per_domain": 10,
        "hunter_monthly_max_searches": 25, "hunter_monthly_max_verifications": 10,
    }
    contact = find_company_contact(_record(), scoring, state, "2026-09")
    assert contact["verification_status"] == "hunter_found_unverified"
    assert contact["confidence"] == "medium"


def test_cached_domain_avoids_http(monkeypatch) -> None:
    _clear_key(monkeypatch)
    monkeypatch.setenv("HUNTER_API_KEY", "key")
    state = _MemoryState()
    state.domains["fixturelabs.example"] = {"result": {"found": False}}
    monkeypatch.setattr(
        hunter.requests, "get",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("cache hit means no HTTP")),
    )
    scoring = {"hunter_enabled": True, "hunter_monthly_max_searches": 25}
    assert find_company_contact(_record(), scoring, state, "2026-09") is None
    assert state.use == {"searches": 0, "verifications": 0}


def test_company_domain_parsing() -> None:
    assert company_domain(_record()) == "fixturelabs.example"
    assert company_domain(_record(company_url="https://www.linkedin.com/company/x")) == ""
    assert company_domain(_record(company_url="https://team@gmail.com")) == ""
    assert company_domain(_record(company_url="not a url")) == ""


def test_pipeline_fills_contactless_record_via_hunter(monkeypatch, tmp_path) -> None:
    import pipeline

    _clear_key(monkeypatch)
    monkeypatch.setenv("HUNTER_API_KEY", "key")
    state = _MemoryState()

    def fake_post(*_a, **_k):
        raise AssertionError("unreachable")

    def fake_get(url, *, params, **_kwargs):
        if url.endswith("/account"):
            return _Response({"data": {"requests": {"searches": {"available": 20}, "verifications": {"available": 0}}}})
        return _Response(_payload())

    monkeypatch.setattr(hunter.requests, "get", fake_get)
    monkeypatch.setattr(
        pipeline, "research_records",
        lambda items, cache=None: [
            {"status": "provisional", "evidence": [], "llm_status": "skipped"} for _ in items
        ],
    )
    monkeypatch.setattr(pipeline, "create_artifacts", lambda items, _root, **_kwargs: items)
    record = {
        "id": "opp-1", "company": "Fixture Labs", "title": "Founder's Office Intern",
        "location": "Bengaluru", "source_url": "https://example.com/j",
        "company_url": "https://fixturelabs.example/careers",
        "discovered_at": "2026-09-11", "score": 90, "research": {},
    }
    scoring = {
        "max_artifacts": 0, "hunter_enabled": True, "hunter_verify": False,
        "hunter_min_confidence": 80, "hunter_limit_per_domain": 10,
        "hunter_monthly_max_searches": 25,
    }
    out = pipeline.enrich_selected(
        [record], tmp_path, 0, {},
        hunter_ctx={"scoring": scoring, "state": state, "month": "2026-09"},
    )
    contact = out[0]["selected_contact"]
    assert contact["email"] == "aarav@fixturelabs.example"
    assert contact["basis"] == "hunter_domain_search"
    assert out[0]["contact_priority"] == "preferred_named"
