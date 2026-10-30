import pandas as pd

from carbonlens.emissions.calculator import estimate_row


def test_no_factor_means_no_estimate():
    row = pd.Series(
        {
            "provider": "aws",
            "service": "compute",
            "region": "us-east-1",
            "usage_quantity": 12,
            "usage_unit": "vCPU-hour",
        }
    )
    result = estimate_row(row)
    assert result.status == "not_estimated"
    assert result.estimated_kg_co2e is None
    assert result.reason
