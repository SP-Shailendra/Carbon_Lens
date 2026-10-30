import pandas as pd
import pytest

from carbonlens.data.validation import validate_usage_frame


def valid_frame():
    return pd.DataFrame(
        {
            "provider": ["aws"],
            "service": ["compute"],
            "region": ["us-east-1"],
            "usage_quantity": [10],
            "usage_unit": ["vCPU-hour"],
            "period_start": ["2026-10-01"],
            "period_end": ["2026-10-31"],
        }
    )


def test_valid_minimal_frame():
    result = validate_usage_frame(valid_frame())
    assert result.valid
    assert not result.errors


def test_missing_required_columns():
    result = validate_usage_frame(pd.DataFrame({"provider": ["aws"]}))
    assert not result.valid
    assert any("Missing required columns" in e for e in result.errors)


def test_negative_usage_rejected():
    frame = valid_frame()
    frame.loc[0, "usage_quantity"] = -1
    result = validate_usage_frame(frame)
    assert not result.valid
    assert any("cannot be negative" in e for e in result.errors)


@pytest.mark.parametrize(
    "column,value",
    [
        ("usage_quantity", float("inf")),
        ("provider", "unknown"),
        ("service", "   "),
        ("period_start", "yesterday"),
        ("period_end", "2026-09-01"),
    ],
)
def test_invalid_parameters_rejected(column, value):
    frame = valid_frame().astype(object)
    frame.loc[0, column] = value
    assert not validate_usage_frame(frame).valid


def test_empty_rows_rejected():
    assert not validate_usage_frame(valid_frame().iloc[:0]).valid


def test_optional_cost_can_be_missing():
    frame = valid_frame()
    frame["cost_amount"] = None
    assert validate_usage_frame(frame).valid


def test_cost_requires_currency_value():
    frame = valid_frame()
    frame["cost_amount"] = 12
    frame["currency"] = None
    assert not validate_usage_frame(frame).valid
