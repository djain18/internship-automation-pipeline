"""Regression test: api/main.py must import cleanly and serve correctly when
api/ is on sys.path but is NOT the current working directory. This is
exactly how modal_app.py's api_web() function loads it (see Task 2) — this
assumption broke silently once already during design review, so it's
pinned here.
"""
from fastapi.testclient import TestClient

import main


def test_main_app_imports_and_serves_health():
    client = TestClient(main.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_main_app_has_expected_routes():
    paths = {route.path for route in main.app.routes}
    assert "/api/listings" in paths
    assert "/api/stats" in paths
    assert "/health" in paths
