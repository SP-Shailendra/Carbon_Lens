import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as strategies

from carbonlens.emissions.calculator import EstimateResult, estimate_row


def bounds(result: EstimateResult) -> tuple[float, float, float]:
    assert result.low_kg_co2e is not None
    assert result.central_kg_co2e is not None
    assert result.high_kg_co2e is not None
    return result.low_kg_co2e, result.central_kg_co2e, result.high_kg_co2e


def usage_row(**changes):
    return pd.Series(
        {
            "provider": "aws",
            "service": "compute",
            "region": "us-east-1",
            "usage_quantity": 1000,
            "usage_unit": "vCPU-hour",
            "period_start": "2026-10-01",
            "period_end": "2026-10-31",
            **changes,
        }
    )


def test_compute_hand_calculated_golden():
    # 1000 vCPUh / 1000 * [0.74, 2.12, 3.5] W * 1.135 PUE * 0.365127796 kg/kWh.
    result = estimate_row(usage_row())
    assert result.method == "estimated_usage"
    assert result.low_kg_co2e == pytest.approx(0.3066708358604)
    assert result.central_kg_co2e == pytest.approx(0.8785705027352)
    assert result.high_kg_co2e == pytest.approx(1.45047016961)
    assert result.provenance and result.range_assumption


def test_storage_hand_calculated_golden():
    # 250 GB-month / 1000 * 744 h / 1000 * midpoint(0.65,1.2) * 1.185 * 0.379069.
    result = estimate_row(
        usage_row(
            provider="azure",
            service="storage",
            region="eastus",
            usage_quantity=250,
            usage_unit="GB-month",
        )
    )
    assert result.central_kg_co2e == pytest.approx(0.07728430341825)
    low, central, high = bounds(result)
    assert low < central < high


def test_provider_never_recalculated_even_with_unsupported_usage():
    result = estimate_row(
        usage_row(
            data_basis="provider_reported",
            provider_kg_co2e=12.345,
            provider_methodology="Provider inventory methodology",
            provider_source_url="https://example.org/provider-report",
            provider_access_date="2026-10-27",
            usage_quantity=999999,
            usage_unit="unsupported",
        )
    )
    assert result.method == "provider_reported"
    assert result.estimated_kg_co2e == 12.345
    assert result.low_kg_co2e == result.central_kg_co2e == result.high_kg_co2e == 12.345
    assert result.provider_methodology == "Provider inventory methodology"


def test_provider_validation_does_not_require_usage():
    from carbonlens.data.validation import validate_usage_frame

    row = usage_row(
        data_basis="provider_reported",
        provider_kg_co2e=12.345,
        provider_methodology="Provider inventory methodology",
        provider_source_url="https://example.org/provider-report",
        provider_access_date="2026-10-27",
    ).drop(["usage_quantity", "usage_unit"])
    assert validate_usage_frame(pd.DataFrame([row])).valid
    row["provider_source_url"] = "not a URL"
    assert not validate_usage_frame(pd.DataFrame([row])).valid


@pytest.mark.parametrize(
    "changes",
    [
        {"usage_unit": "USD"},
        {"service": "gpu"},
        {"region": "unconfigured"},
        {"accounting_method": "market_based"},
        {"period_end": "2027-01-01"},
    ],
)
def test_unsupported_usage_is_not_estimated(changes):
    result = estimate_row(usage_row(**changes))
    assert result.method == "not_estimated"
    assert result.low_kg_co2e is result.central_kg_co2e is result.high_kg_co2e is None


def test_provider_only_csv_and_separate_accounting_totals():
    from carbonlens.agent import analyze_usage
    from carbonlens.models.schemas import AnalysisReport

    row = {
        "provider": "aws",
        "service": "compute",
        "region": "global",
        "period_start": "2026-10-01",
        "period_end": "2026-10-31",
        "data_basis": "provider_reported",
        "provider_kg_co2e": 12.345,
        "provider_methodology": "Provider official inventory v1",
        "provider_source_url": "https://example.org/report",
        "provider_access_date": "2026-10-27",
        "accounting_method": "market_based",
    }
    report = analyze_usage(pd.DataFrame([row]).to_csv(index=False).encode())
    assert report["rows"][0]["central_kg_co2e"] == 12.345
    assert report["recommendations"] == []
    AnalysisReport.model_validate(report)
    mixed = analyze_usage(pd.DataFrame([row, usage_row().to_dict()]).to_csv(index=False).encode())
    assert mixed["summary"]["estimated_kg_co2e"] is None
    assert len(mixed["summary"]["totals_by_method"]) == 2
    assert mixed["summary"]["coverage_percent"] == 100
    ignored_usage = analyze_usage(
        pd.DataFrame([{**row, "usage_quantity": "not activity data", "usage_unit": "irrelevant"}])
        .to_csv(index=False)
        .encode()
    )
    assert ignored_usage["rows"][0]["central_kg_co2e"] == 12.345
    assert ignored_usage["rows"][0]["usage_quantity"] is None


def test_mixed_normalized_sample_has_sourced_ranges():
    from pathlib import Path

    from carbonlens.agent import analyze_usage
    from carbonlens.models.schemas import AnalysisReport

    sample = Path(__file__).resolve().parents[1] / "data" / "sample_cloud_usage.csv"
    report = analyze_usage(sample.read_bytes())
    assert report["summary"]["coverage_percent"] == 100
    assert len(report["recommendations"]) == 3
    for row in report["rows"]:
        assert row["method"] == "estimated_usage"
        assert row["low_kg_co2e"] <= row["central_kg_co2e"] <= row["high_kg_co2e"]
        assert row["range_assumption"] and row["provenance"]
    AnalysisReport.model_validate(report)


@settings(max_examples=60, deadline=None)
@given(
    quantity=strategies.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False),
    increment=strategies.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False),
)
def test_property_compute_is_monotone_and_ranges_ordered(quantity, increment):
    first = estimate_row(usage_row(usage_quantity=quantity))
    second = estimate_row(usage_row(usage_quantity=quantity + increment))
    first_values, second_values = bounds(first), bounds(second)
    assert 0 <= first_values[0] <= first_values[1] <= first_values[2]
    assert all(before <= after for before, after in zip(first_values, second_values))


@settings(max_examples=50, deadline=None)
@given(
    quantity=strategies.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False)
)
def test_property_storage_units_are_equivalent(quantity):
    gb = estimate_row(usage_row(service="storage", usage_quantity=quantity, usage_unit="GB-hour"))
    tb = estimate_row(
        usage_row(service="storage", usage_quantity=quantity / 1000, usage_unit="TB-hour")
    )
    assert gb.central_kg_co2e == pytest.approx(tb.central_kg_co2e)
    low, central, high = bounds(gb)
    assert low <= central <= high


@settings(max_examples=40, deadline=None)
@given(unit=strategies.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=30))
def test_property_incompatible_units_never_get_a_number(unit):
    result = estimate_row(usage_row(usage_unit=unit))
    assert result.method == "not_estimated"
    assert result.central_kg_co2e is None


@pytest.mark.parametrize("unit", ["Gb-hour", "gb-hour", "GiB-hour", "GiB-month", "GB-second", "GB"])
def test_storage_unit_case_and_dimensions_are_not_guessed(unit):
    result = estimate_row(usage_row(service="storage", usage_unit=unit))
    assert result.method == "not_estimated"
    assert result.central_kg_co2e is None


def test_direct_factor_units_are_case_sensitive():
    result = estimate_row(
        usage_row(
            usage_unit="kwh",
            period_start="2023-10-01",
            period_end="2023-10-31",
            energy_basis="facility",
            energy_source="Test measurement reference",
        )
    )
    assert result.method == "not_estimated"
    assert result.reason is not None and "case-sensitive" in result.reason


@pytest.mark.parametrize(
    "region,intensity", [("asia-south1", 0.598), ("asia-south2", 0.473), ("us-central1", 0.432)]
)
def test_google_published_regions_golden(region, intensity):
    result = estimate_row(usage_row(provider="gcp", region=region))
    assert result.central_kg_co2e == pytest.approx(2.485 * 1.1 * intensity)
    assert result.provenance[0]["data_year"] == 2025


def test_unverified_factor_is_not_used(monkeypatch):
    from dataclasses import replace

    from carbonlens.emissions.factors import EMISSION_FACTORS

    key = "aws|*|us-east-1|kwh"
    monkeypatch.setitem(EMISSION_FACTORS, key, replace(EMISSION_FACTORS[key], verified=False))
    assert estimate_row(usage_row()).method == "not_estimated"


def test_provider_bounds_retained_and_never_used_for_recommendations():
    row = usage_row(
        data_basis="provider_reported",
        provider_kg_co2e=12.345,
        provider_low_kg_co2e=10,
        provider_high_kg_co2e=20,
        provider_methodology="Provider label",
        provider_source_url="https://example.org/report",
        provider_access_date="2026-10-27",
    )
    result = estimate_row(row)
    assert (result.low_kg_co2e, result.central_kg_co2e, result.high_kg_co2e) == (10, 12.345, 20)


def test_registry_supports_disjoint_versions_and_rejects_overlap(tmp_path, monkeypatch):
    import json

    from carbonlens.emissions import factors

    monkeypatch.setattr(factors, "EMISSION_FACTORS", {})
    monkeypatch.setattr(factors, "USAGE_PROFILES", {})
    monkeypatch.setattr(factors, "REGISTRY_INFO", {})
    source = json.loads(factors.REGISTRY_PATH.read_bytes())["factors"][0]
    updated = {
        **source,
        "factor_id": "next-version",
        "valid_from": "2024-01-01",
        "valid_to": "2024-12-31",
    }
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps({"schema_version": 2, "registry_version": "test", "factors": [source, updated]})
    )
    factors.load_factor_file(str(path))
    assert len(factors.EMISSION_FACTORS) == 2
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "registry_version": "test",
                "factors": [source, {**updated, "valid_from": "2023-01-01"}],
            }
        )
    )
    with pytest.raises(ValueError, match="nonoverlapping"):
        factors.load_factor_file(str(path))
    assert len(factors.EMISSION_FACTORS) == 2


@pytest.mark.parametrize("medium,expected", [("hdd", 0.65), ("ssd", 1.2)])
def test_known_storage_medium_has_explicit_point_scenario(medium, expected):
    result = estimate_row(
        usage_row(
            service="storage", usage_unit="TB-hour", usage_quantity=1000, storage_medium=medium
        )
    )
    low, central, high = bounds(result)
    assert low == central == high == pytest.approx(expected * 1.135 * 0.365127796)


def test_ambiguous_gb_month_period_is_refused():
    result = estimate_row(
        usage_row(service="storage", usage_unit="GB-month", period_start="2026-10-02")
    )
    assert result.method == "not_estimated"
    assert result.reason is not None
    assert "complete calendar month" in result.reason


@pytest.mark.parametrize(
    "changes", [{"low_kg_co2e": 5}, {"central_kg_co2e": float("inf")}, {"range_assumption": None}]
)
def test_numeric_schema_requires_complete_ordered_ranges(changes):
    from carbonlens.models.schemas import RangedResult

    with pytest.raises(ValueError):
        RangedResult.model_validate(
            {
                "method": "estimated_usage",
                "low_kg_co2e": 1,
                "central_kg_co2e": 2,
                "high_kg_co2e": 3,
                "range_assumption": "scenario",
                **changes,
            }
        )
