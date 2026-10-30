import sqlite3
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from carbonlens.api import create_app
from carbonlens.config import Settings
from carbonlens.emissions.factors import EMISSION_FACTORS, EmissionFactor


@pytest.fixture
def config(tmp_path):
    return Settings(database_path=str(tmp_path / "test.db"), api_key="test-key", factors_path="")


@pytest.fixture
def client(config):
    with TestClient(create_app(config), headers={"X-API-Key": "test-key"}) as client:
        yield client


@pytest.fixture
def factor(monkeypatch):
    monkeypatch.setattr("carbonlens.emissions.calculator.USAGE_PROFILES", {})
    monkeypatch.setitem(
        EMISSION_FACTORS,
        "aws|compute|us-east-1|vcpu-hour",
        EmissionFactor(
            factor_id="synthetic-test-only",
            value=0.5,
            unit="kgCO2e/vCPU-hour",
            source_name="Synthetic test fixture, not for real estimates",
            source_url="https://example.org/test",
            geography="us-east-1",
            valid_from="2026-01-01",
            valid_to="2026-12-31",
            version="test",
            verified=True,
            access_date="2026-10-27",
        ),
    )


def test_health_and_auth(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/v1/config", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/v1/config").json()["executes_cloud_changes"] is False


def test_sample_report_persisted(client, config):
    response = client.post("/api/v1/analyses/sample")
    assert response.status_code == 201
    report = response.json()
    assert report["summary"]["estimated_kg_co2e"] == pytest.approx(0.277182523746474)
    assert report["summary"]["coverage_percent"] == 100
    assert report["summary"]["costs_by_currency"] == {"USD": 35.75}
    assert client.get(f"/api/v1/analyses/{report['id']}").json() == report
    assert client.get("/api/v1/analyses").json()[0]["id"] == report["id"]
    with TestClient(create_app(config), headers={"X-API-Key": "test-key"}) as restarted:
        assert restarted.get(f"/api/v1/analyses/{report['id']}").status_code == 200


def test_grounded_estimate_and_idempotent_decision(client, config, factor):
    report = client.post("/api/v1/analyses/sample").json()
    assert report["summary"]["estimated_kg_co2e"] == 60
    assert report["summary"]["estimated_rows"] == 1
    assert report["rows"][0]["factor"]["factor_id"] == "synthetic-test-only"
    recommendation = report["recommendations"][0]
    assert recommendation["evidence"]
    assert recommendation["risks"]
    assert recommendation["next_steps"]
    assert recommendation["potential_savings_kg_co2e"] is None
    assert recommendation["savings_reason"]
    payload = {"recommendation_id": "hotspot-1", "decision": "approved"}
    path = f"/api/v1/analyses/{report['id']}/decisions"
    assert client.post(path, json=payload).json()["recommendations"][0]["decision"] == "approved"
    assert client.post(path, json=payload).status_code == 200
    with sqlite3.connect(config.database_path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM events WHERE name='recommendation_approved'"
            ).fetchone()[0]
            == 1
        )
    assert client.post(path, json={**payload, "decision": "execute"}).status_code == 422
    assert client.post(path, json={**payload, "recommendation_id": "missing"}).status_code == 404


def test_upload_validation_and_parameter_bounds(client):
    assert client.post("/api/v1/analyses", files={"file": ("bad.csv", b"x\n1")}).status_code == 422
    assert client.post("/api/v1/analyses", files={"file": ("bad.txt", b"x\n1")}).status_code == 415
    assert client.post("/api/v1/analyses/sample?top_n=4").status_code == 422
    assert client.get("/api/v1/analyses/00000000-0000-0000-0000-000000000000").status_code == 404


def test_large_upload_rejected(config):
    with TestClient(
        create_app(replace(config, max_upload_mb=1)), headers={"X-API-Key": "test-key"}
    ) as client:
        response = client.post(
            "/api/v1/analyses", files={"file": ("large.csv", b"x" * (1024 * 1024 + 1))}
        )
        assert response.status_code == 413


def test_invalid_ai_response_retains_deterministic_numbers(client, factor, monkeypatch):
    def invalid(*args, **kwargs):
        raise ValueError("malformed model response")

    monkeypatch.setattr("carbonlens.api.explain_hotspots", invalid)
    report = client.post("/api/v1/analyses/sample?use_ai=true").json()
    assert report["summary"]["estimated_kg_co2e"] == 60
    assert report["explanation_mode"] == "deterministic"
    assert report["warnings"]


def test_analytics_rejects_raw_properties(client):
    assert client.post("/api/v1/events", json={"name": "onboarding_started"}).status_code == 200
    assert (
        client.post(
            "/api/v1/events", json={"name": "report_viewed", "report_id": "missing"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/events", json={"name": "onboarding_started", "raw_csv": "private"}
        ).status_code
        == 422
    )


@pytest.mark.ui
@pytest.mark.parametrize(
    "sample_label,expected_total",
    [
        ("Mixed usage", 60),
        ("AWS electricity (2023)", 87.632145216),
    ],
)
def test_dashboard_sample_views_and_approval(
    client, factor, monkeypatch, sample_label, expected_total
):
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    class LocalClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, path, **kwargs):
            return client.request(method, path, **kwargs)

    monkeypatch.setattr("httpx.Client", lambda **kwargs: LocalClient())
    dashboard = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30
    ).run()
    assert not dashboard.exception
    dashboard.segmented_control(key="sample_dataset").set_value(sample_label).run()
    next(button for button in dashboard.button if button.label == "Analyze sample").click().run()
    assert not dashboard.exception
    assert dashboard.session_state["report"]["summary"]["estimated_kg_co2e"] == pytest.approx(
        expected_total
    )
    assert dashboard.session_state["report"]["data_origin"] == "synthetic_sample"
    assert any(
        "low_kg_co2e" in table.value.columns and "method" in table.value.columns
        for table in dashboard.dataframe
    )
    for view in ("Usage & provenance", "Methodology", "Recommendations"):
        dashboard.segmented_control(key="report_view").set_value(view).run()
        assert not dashboard.exception
    next(button for button in dashboard.button if button.label == "Approve").click().run()
    assert not dashboard.exception
    assert dashboard.session_state["report"]["recommendations"][0]["decision"] == "approved"
    next(button for button in dashboard.button if button.label == "Reject").click().run()
    assert not dashboard.exception
    assert dashboard.session_state["report"]["recommendations"][0]["decision"] == "rejected"


def test_reference_api_profile_persists_provenance(client):
    response = client.post("/api/v1/analyses/sample?profile=aws-electricity-2023&top_n=2")
    assert response.status_code == 201
    report = response.json()
    assert report["summary"]["estimated_kg_co2e"] == pytest.approx(87.632145216)
    assert len(report["recommendations"]) == 2
    assert report["data_origin"] == "synthetic_sample"
    assert "Synthetic" in report["warnings"][0]
    assert client.get(f"/api/v1/analyses/{report['id']}").json() == report
    assert client.post("/api/v1/analyses/sample?profile=unknown").status_code == 422


def test_v2_registry_and_csv_include_ranges_and_sources(client):
    import csv
    import io
    import json

    registry = client.get("/api/v1/registry").json()
    assert registry["registry_version"]
    assert registry["usage_profiles"]
    report = client.post("/api/v1/analyses/sample").json()
    response = client.get(f"/api/v1/analyses/{report['id']}/csv")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 3
    assert rows[0]["method"] == "estimated_usage"
    assert (
        float(rows[0]["low_kg_co2e"])
        <= float(rows[0]["central_kg_co2e"])
        <= float(rows[0]["high_kg_co2e"])
    )
    assert json.loads(rows[0]["provenance"])[0]["source_url"]
    assert rows[0]["range_assumption"]


def test_provider_upload_preserves_figure_and_source_without_usage(client):
    import pandas as pd

    row = {
        "provider": "gcp",
        "service": "compute",
        "region": "global",
        "period_start": "2026-10-01",
        "period_end": "2026-10-31",
        "data_basis": "provider_reported",
        "provider_kg_co2e": 12.345,
        "provider_methodology": "Provider supplied label",
        "provider_source_url": "https://example.org/report",
        "provider_access_date": "2026-10-27",
        "accounting_method": "market_based",
    }
    content = pd.DataFrame([row]).to_csv(index=False).encode()
    response = client.post("/api/v1/analyses", files={"file": ("provider.csv", content)})
    assert response.status_code == 201
    report = response.json()
    assert report["rows"][0]["method"] == "provider_reported"
    assert report["rows"][0]["central_kg_co2e"] == 12.345
    assert report["rows"][0]["provider_methodology"] == row["provider_methodology"]
    assert report["rows"][0]["provenance"][0]["verified"] is False
    assert not report["recommendations"]
    for column, value in (
        ("provider_kg_co2e", -1),
        ("provider_source_url", "bad"),
        ("provider_methodology", None),
        ("provider_low_kg_co2e", 10),
    ):
        invalid = pd.DataFrame([{**row, column: value}]).to_csv(index=False).encode()
        assert (
            client.post("/api/v1/analyses", files={"file": ("provider.csv", invalid)}).status_code
            == 422
        )


def test_legacy_reports_are_not_presented_as_ranged(client):
    report = client.post("/api/v1/analyses/sample").json()
    report.pop("methodology_version")
    import json

    with sqlite3.connect(client.app.state.store.path) as connection:
        connection.execute(
            "UPDATE reports SET payload=? WHERE id=?", (json.dumps(report), report["id"])
        )
    assert client.get(f"/api/v1/analyses/{report['id']}").status_code == 409
    assert client.get(f"/api/v1/analyses/{report['id']}/csv").status_code == 409
    assert client.get("/api/v1/analyses").json()[0]["summary"]["estimated_kg_co2e"] is None


def test_factor_file_contract_and_validity(tmp_path, monkeypatch):
    import json

    from carbonlens.agent import analyze_usage
    from carbonlens.emissions.factors import load_factor_file

    registry: dict[str, EmissionFactor] = {}
    monkeypatch.setattr("carbonlens.emissions.factors.EMISSION_FACTORS", registry)
    monkeypatch.setattr("carbonlens.emissions.factors.USAGE_PROFILES", {})
    monkeypatch.setattr("carbonlens.emissions.calculator.USAGE_PROFILES", {})
    definition = {
        "factor_id": "synthetic-only",
        "provider": "aws",
        "service": "compute",
        "region": "us-east-1",
        "input_unit": "vCPU-hour",
        "value": 0.5,
        "unit": "kgCO2e/vCPU-hour",
        "source_name": "Synthetic test",
        "source_url": "https://example.org/test",
        "geography": "us-east-1",
        "valid_from": "2026-01-01",
        "valid_to": "2026-12-31",
        "version": "test",
        "notes": "Not a real factor",
        "verified": True,
        "access_date": "2026-10-27",
    }
    path = tmp_path / "factors.json"
    path.write_text(json.dumps([{**definition, "unit": "kgCO2e/USD"}]))
    with pytest.raises(ValueError, match="unit must be"):
        load_factor_file(str(path))
    path.write_text(json.dumps([definition, definition]))
    with pytest.raises(ValueError, match="unique"):
        load_factor_file(str(path))
    from carbonlens.emissions.factors import FactorDefinition

    assert FactorDefinition.model_validate(definition).valid_to.year == 2026
    path.write_text(json.dumps([definition]))
    load_factor_file(str(path))
    from pathlib import Path

    report = analyze_usage(
        (Path(__file__).resolve().parents[1] / "data" / "sample_cloud_usage.csv").read_bytes()
    )
    assert report["summary"]["estimated_kg_co2e"] == 60


def test_expired_factor_not_estimated(client, factor, monkeypatch):
    current = EMISSION_FACTORS["aws|compute|us-east-1|vcpu-hour"]
    monkeypatch.setitem(
        EMISSION_FACTORS, "aws|compute|us-east-1|vcpu-hour", replace(current, valid_to="2026-09-30")
    )
    report = client.post("/api/v1/analyses/sample").json()
    assert report["summary"]["estimated_kg_co2e"] is None
    assert "outside factor validity" in report["rows"][0]["reason"]


@pytest.mark.parametrize(
    "content",
    [
        '{"recommendations":[{"id":"hotspot-1","action":"review_schedule"}]}',
        '{"recommendations":[{"id":"unknown","action":"review_schedule"}]}',
        '{"recommendations":[{"id":"hotspot-1","action":"review_storage_lifecycle"}]}',
        '{"recommendations":[{"id":"hotspot-1","action":"review_schedule","invented_savings":999}]}',
        "not json",
    ],
)
def test_ai_schema_and_minimal_payload(content, monkeypatch):
    import httpx

    from carbonlens.recommendations.llm_explainer import explain_hotspots

    original_client = httpx.Client
    captured = []

    def respond(request):
        import json

        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(
        "carbonlens.recommendations.llm_explainer.httpx.Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond)),
    )
    config = Settings(llm_provider="openai", llm_api_key="test-not-a-real-key")
    recommendation = {
        "id": "hotspot-1",
        "estimated_kg_co2e": 60,
        "allowed_actions": ["review_schedule"],
        "raw_upload": "private",
    }
    if content == '{"recommendations":[{"id":"hotspot-1","action":"review_schedule"}]}':
        assert explain_hotspots([recommendation], config)[0]["action"] == "review_schedule"
    else:
        with pytest.raises(ValueError):
            explain_hotspots([recommendation], config)
    assert "private" not in str(captured)
