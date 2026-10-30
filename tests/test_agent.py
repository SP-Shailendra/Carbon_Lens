from pathlib import Path

import pytest

from carbonlens.agent import AnalysisError, analyze_usage
from carbonlens.models.schemas import AnalysisReport

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample_cloud_usage.csv"


def test_agent_does_not_invent_estimates_or_recommendations(monkeypatch):
    monkeypatch.setattr("carbonlens.emissions.factors.EMISSION_FACTORS", {})
    monkeypatch.setattr("carbonlens.emissions.calculator.USAGE_PROFILES", {})
    report = analyze_usage(SAMPLE.read_bytes())
    assert report["summary"]["total_rows"] == 3
    assert report["summary"]["estimated_kg_co2e"] is None
    assert report["summary"]["not_estimated_rows"] == 3
    assert report["recommendations"] == []
    assert all(row["factor"] is None for row in report["rows"])


def test_agent_returns_actionable_validation_errors():
    with pytest.raises(AnalysisError, match="Missing required columns"):
        analyze_usage(b"hello\nworld\n")


def test_agent_rejects_empty_file():
    with pytest.raises(AnalysisError, match="valid UTF-8 CSV"):
        analyze_usage(b"")


def electricity_csv(**changes):
    import pandas as pd

    row = {
        "provider": "aws",
        "service": "compute",
        "region": "us-east-1",
        "usage_quantity": 100,
        "usage_unit": "kWh",
        "period_start": "2023-10-01",
        "period_end": "2023-10-31",
        "energy_basis": "facility",
        "energy_source": "Synthetic test evidence",
    }
    return pd.DataFrame([{**row, **changes}]).to_csv(index=False).encode()


def test_primary_source_reference_calculation_and_provenance():
    report = analyze_usage(electricity_csv())
    assert report["summary"]["estimated_kg_co2e"] == pytest.approx(36.51339384)
    assert report["summary"]["coverage_percent"] == 100
    assert report["rows"][0]["factor"]["value"] == 0.3651339384
    assert "NRL23/SERC/NRC2ERTA" in report["rows"][0]["factor"]["version"]
    assert report["warnings"]
    assert report["recommendations"][0]["potential_savings_kg_co2e"] is None
    AnalysisReport.model_validate(report)


def test_default_registry_preserves_verified_historical_reference():
    from carbonlens.emissions.factors import EMISSION_FACTORS

    factor = EMISSION_FACTORS["aws|compute|us-east-1|kwh"]
    assert factor.value == 0.3651339384
    assert factor.verified is True
    assert factor.access_date == "2026-10-26"
    assert factor.method == "location_based"


@pytest.mark.parametrize(
    "changes",
    [
        {"usage_unit": "USD"},
        {"region": "us-west-2"},
        {"provider": "gcp"},
        {"service": "storage"},
        {"period_start": "2026-10-01", "period_end": "2026-10-31"},
        {"period_start": "2023-12-01", "period_end": "2024-01-01"},
        {"energy_basis": "it"},
        {"energy_basis": None},
        {"energy_source": None},
        {"energy_source": "   "},
    ],
)
def test_reference_refuses_unsupported_inputs(changes):
    report = analyze_usage(electricity_csv(**changes))
    assert report["summary"]["estimated_kg_co2e"] is None
    assert not report["recommendations"]


def test_reference_sample_is_synthetic_and_top_n_is_respected():
    report = analyze_usage(
        (SAMPLE.parent / "sample_aws_electricity_2023.csv").read_bytes(), top_n=2
    )
    assert report["summary"]["estimated_kg_co2e"] == pytest.approx(87.632145216)
    assert len(report["recommendations"]) == 2
    assert all("SYNTHETIC" in row["energy_source"] for row in report["rows"])
