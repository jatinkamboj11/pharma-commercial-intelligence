"""API tests - run against the generated sample warehouse.

    python etl/generate_sample_data.py && python etl/load_data.py
    pytest -q
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_territories_have_kpis_and_ranks():
    body = client.get("/api/territories").json()
    ts = body["territories"]
    assert len(ts) >= 10
    first = ts[0]
    for key in ["territory_name", "rep_name", "prescribers", "claims",
                "drug_cost", "claims_rank", "claims_yoy_pct"]:
        assert key in first
    assert first["claims_rank"] == 1  # sorted by claims desc


def test_territory_performance_and_404():
    tid = client.get("/api/territories").json()["territories"][0]["territory_id"]
    body = client.get(f"/api/territories/{tid}/performance").json()
    assert body["territory"]["territory_id"] == tid
    assert len(body["trend"]) >= 2
    assert len(body["top_drugs"]) > 0
    assert client.get("/api/territories/999999/performance").status_code == 404


def test_prescriber_deciles_range_and_filters():
    body = client.get("/api/prescribers", params={"min_decile": 9, "limit": 20}).json()
    assert body["total"] > 0
    assert all(9 <= p["decile"] <= 10 for p in body["prescribers"])
    # top of the claims sort should be decile 10
    assert body["prescribers"][0]["decile"] == 10


def test_prescriber_profile():
    p = client.get("/api/prescribers", params={"limit": 1}).json()["prescribers"][0]
    body = client.get(f"/api/prescribers/{p['npi']}").json()
    assert body["prescriber"]["npi"] == p["npi"]
    assert body["decile"] == p["decile"]
    assert len(body["drug_mix"]) > 0


def test_bad_sort_rejected():
    r = client.get("/api/prescribers", params={"sort": "npi; DROP TABLE"})
    assert r.status_code == 400


def test_decile_concentration_insight():
    body = client.get("/api/insights/deciles").json()
    assert len(body["deciles"]) == 10
    shares = [b["claims_share_pct"] for b in body["deciles"]]
    assert abs(sum(shares) - 100) < 1.5
    # the whole business premise: volume concentrates at the top
    assert body["top3_decile_claims_share_pct"] > 40


def test_call_plan_more_calls_more_coverage():
    tid = client.get("/api/territories").json()["territories"][0]["territory_id"]
    small = client.post("/api/insights/call-plan",
                        json={"territory_id": tid, "calls_available": 50}).json()
    big = client.post("/api/insights/call-plan",
                      json={"territory_id": tid, "calls_available": 2000}).json()
    assert big["claims_coverage_pct"] >= small["claims_coverage_pct"]
    assert small["allocation"][0]["decile"] == 10  # greedy starts at the top


def test_drug_market_share():
    drugs = client.get("/api/drugs").json()["drugs"]
    top = drugs[0]
    body = client.get(f"/api/drugs/{top['drug_id']}/market").json()
    assert body["drug"] == top["brand_name"]
    assert len(body["by_territory"]) > 0


def test_dashboard_pages_render():
    for path in ["/", "/targeting", "/territory/1"]:
        r = client.get(path)
        assert r.status_code == 200
        assert "<html" in r.text
