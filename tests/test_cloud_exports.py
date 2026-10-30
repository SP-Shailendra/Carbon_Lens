import pandas as pd

from carbonlens.data.cloud_exports import normalize_cloud_export
from carbonlens.data.csv_loader import load_csv
from carbonlens.data.validation import validate_usage_frame
from carbonlens.emissions.calculator import estimate_row


def normalize(provider, payload):
    content, warnings = normalize_cloud_export(payload.encode(), provider)
    frame = load_csv(content)
    assert validate_usage_frame(frame).valid
    return frame, warnings


def test_aws_cur_maps_vcpu_hours_and_storage_months():
    frame, warnings = normalize(
        "aws",
        "product_servicecode,product_region,line_item_usage_start_date,line_item_usage_end_date,line_item_usage_amount,pricing_unit,line_item_unblended_cost,line_item_currency_code,product_vcpu\n"
        "AmazonEC2,us-east-1,2026-10-01T00:00:00Z,2026-10-02T00:00:00Z,3,Hrs,4.5,USD,2\n"
        "AmazonS3,us-east-1,2026-10-01T00:00:00Z,2026-11-01T00:00:00Z,12,GB-Mo,1.2,USD,\n",
    )
    assert frame["usage_quantity"].tolist() == [6, 12]
    assert frame["usage_unit"].tolist() == ["vCPU-hour", "GB-month"]
    assert frame["service"].tolist() == ["compute", "storage"]
    assert frame["period_end"].tolist() == ["2026-10-01", "2026-10-31"]
    assert warnings == []


def test_azure_unmapped_hour_unit_is_not_estimated():
    frame, warnings = normalize(
        "azure",
        "MeterCategory,ResourceLocation,Date,Quantity,UnitOfMeasure,CostInBillingCurrency,BillingCurrency\n"
        'Virtual Machines,eastus,2026-10-01,2,"1 Hour",3.5,USD\n',
    )
    assert frame.loc[0, "usage_unit"] == "1 Hour"
    assert estimate_row(frame.iloc[0]).status == "not_estimated"
    assert warnings == []


def test_azure_billing_period_end_date_is_inclusive():
    frame, warnings = normalize(
        "azure",
        "MeterCategory,ResourceLocation,BillingPeriodStartDate,BillingPeriodEndDate,Quantity,UnitOfMeasure,CostInBillingCurrency,BillingCurrency\n"
        "Storage,eastus,2026-10-01,2026-10-31,10,GB/Month,3.5,USD\n",
    )
    assert frame.loc[0, "period_start"] == "2026-10-01"
    assert frame.loc[0, "period_end"] == "2026-10-31"
    assert frame.loc[0, "usage_unit"] == "GB-month"
    assert warnings == []


def test_gcp_cost_only_rows_do_not_infer_emissions_from_spend():
    frame, warnings = normalize(
        "gcp",
        "service.description,location.region,usage_start_time,usage_end_time,cost,currency\n"
        "Cloud Storage,us-central1,2026-10-01T00:00:00Z,2026-10-02T00:00:00Z,8.25,USD\n",
    )
    assert pd.isna(frame.loc[0, "usage_quantity"])
    assert frame.loc[0, "data_basis"] == "cost_only"
    result = estimate_row(frame.iloc[0])
    assert result.status == "not_estimated"
    assert result.reason is not None
    assert "not inferred from spend" in result.reason
    assert warnings == ["1 cost-only rows are retained without inferring emissions from spend."]


def test_negative_cost_adjustment_is_excluded_with_warning():
    frame, warnings = normalize(
        "gcp",
        "service.description,location.region,usage_start_time,usage_end_time,usage.amount,usage.unit,cost,currency\n"
        "Compute Engine,us-central1,2026-10-01T00:00:00Z,2026-10-02T00:00:00Z,2,vCPU-hour,-1,USD\n",
    )
    assert frame.loc[0, "usage_quantity"] == 2
    assert pd.isna(frame.loc[0, "cost_amount"])
    assert warnings == [
        "1 negative-cost adjustment rows were excluded from cost totals; usage is retained when available."
    ]
