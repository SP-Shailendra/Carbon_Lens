import math
from datetime import timedelta
from io import BytesIO
from typing import Literal

import pandas as pd

CloudProvider = Literal["aws", "azure", "gcp"]

NORMALIZED_COLUMNS = [
    "provider",
    "service",
    "region",
    "usage_quantity",
    "usage_unit",
    "period_start",
    "period_end",
    "cost_amount",
    "currency",
    "data_basis",
]

EXPORT_COLUMNS = {
    "aws": {
        "service": ("product_servicecode", "line_item_product_code"),
        "region": ("product_region", "line_item_availability_zone"),
        "start": ("line_item_usage_start_date",),
        "end": ("line_item_usage_end_date",),
        "quantity": ("line_item_usage_amount",),
        "unit": ("pricing_unit", "line_item_usage_unit"),
        "cost": ("line_item_unblended_cost",),
        "currency": ("line_item_currency_code",),
        "vcpu": ("product_vcpu", "product_vcpus"),
    },
    "azure": {
        "service": ("MeterCategory", "ServiceName"),
        "region": ("ResourceLocation", "ResourceLocationNormalized"),
        "start": ("Date", "UsageDateTime", "BillingPeriodStartDate"),
        "end": ("Date", "UsageDateTime", "BillingPeriodEndDate"),
        "quantity": ("Quantity", "UsageQuantity"),
        "unit": ("UnitOfMeasure", "Unit"),
        "cost": ("CostInBillingCurrency", "PreTaxCost"),
        "currency": ("BillingCurrency", "Currency"),
    },
    "gcp": {
        "service": ("service.description", "service_description"),
        "region": ("location.region", "location_region", "region"),
        "start": ("usage_start_time",),
        "end": ("usage_end_time",),
        "quantity": ("usage.amount", "usage_amount"),
        "unit": ("usage.unit", "usage_unit"),
        "cost": ("cost",),
        "currency": ("currency",),
    },
}


class CloudExportError(ValueError):
    pass


def _column(columns: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    return next(
        (columns[alias.casefold()] for alias in aliases if alias.casefold() in columns), None
    )


def _value(row: pd.Series, column: str | None) -> str:
    if column is None or pd.isna(row[column]):
        return ""
    return str(row[column]).strip()


def _number(value: str) -> float | None:
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _date_range(start: str, end: str, end_exclusive: bool) -> tuple[str, str] | None:
    start_time = pd.to_datetime(start, utc=True, errors="coerce")
    if pd.isna(start_time):
        return None
    start_day = start_time.date()
    end_time = pd.to_datetime(end, utc=True, errors="coerce") if end else start_time
    if pd.isna(end_time) or end_time < start_time:
        return None
    end_day = end_time.date()
    if (
        end_exclusive
        and end_time > start_time
        and (end_time.hour, end_time.minute, end_time.second) == (0, 0, 0)
    ):
        end_day -= timedelta(days=1)
    if end_day < start_day:
        end_day = start_day
    return start_day.isoformat(), end_day.isoformat()


def _service(provider: CloudProvider, value: str) -> str:
    normalized = value.casefold()
    if provider == "aws":
        if "ec2" in normalized:
            return "compute"
        if "s3" in normalized or "ebs" in normalized:
            return "storage"
    elif provider == "azure":
        if "virtual machine" in normalized or "compute" in normalized:
            return "compute"
        if "storage" in normalized or "managed disk" in normalized:
            return "storage"
    elif provider == "gcp":
        if "compute engine" in normalized or "kubernetes engine" in normalized:
            return "compute"
        if "cloud storage" in normalized:
            return "storage"
    return value[:200] or "unknown"


def _unit(provider: CloudProvider, value: str) -> str:
    normalized = value.casefold().replace(" ", "").replace("_", "-")
    common = {
        "vcpu-hour": "vCPU-hour",
        "vcpu-hours": "vCPU-hour",
        "gb-hour": "GB-hour",
        "gb-hours": "GB-hour",
        "gb-month": "GB-month",
        "gb-months": "GB-month",
        "tb-hour": "TB-hour",
        "tb-hours": "TB-hour",
    }
    if normalized in common:
        return common[normalized]
    provider_units = {
        "aws": {
            "gb-mo": "GB-month",
            "gb-hrs": "GB-hour",
            "tb-hrs": "TB-hour",
        },
        "azure": {"gb/month": "GB-month", "gb/hour": "GB-hour"},
        "gcp": {},
    }
    return provider_units[provider].get(normalized, value[:100])


def normalize_cloud_export(file_bytes: bytes, provider: CloudProvider) -> tuple[bytes, list[str]]:
    """Normalize common AWS CUR, Azure Cost Management, or GCP Billing CSV exports."""
    try:
        frame = pd.read_csv(BytesIO(file_bytes), nrows=50_001)
    except (ValueError, UnicodeError, pd.errors.ParserError) as error:
        raise CloudExportError("Upload a valid UTF-8 provider export CSV.") from error
    if frame.empty:
        raise CloudExportError("The provider export contains no rows.")
    if len(frame) > 50_000:
        raise CloudExportError("Provider export exceeds the 50,000-row limit.")
    if provider not in EXPORT_COLUMNS:
        raise CloudExportError("Unsupported cloud provider export.")

    columns = {str(name).strip().casefold(): str(name) for name in frame.columns}
    source = EXPORT_COLUMNS[provider]
    resolved = {name: _column(columns, aliases) for name, aliases in source.items()}
    for required in ("service", "region", "start"):
        if resolved[required] is None:
            raise CloudExportError(
                f"The {provider.upper()} export is missing a supported {required} column."
            )

    rows = []
    skipped = 0
    cost_adjustments = 0
    cost_only = 0
    for _, source_row in frame.iterrows():
        dates = _date_range(
            _value(source_row, resolved["start"]),
            _value(source_row, resolved["end"]),
            end_exclusive=provider in {"aws", "gcp"},
        )
        service_name = _value(source_row, resolved["service"])
        region = _value(source_row, resolved["region"])
        if dates is None or not service_name or not region:
            skipped += 1
            continue

        quantity = _number(_value(source_row, resolved["quantity"]))
        unit = _unit(provider, _value(source_row, resolved["unit"]))
        if (
            provider == "aws"
            and _service(provider, service_name) == "compute"
            and unit.casefold() in {"hrs", "hr", "hour", "hours"}
        ):
            vcpus = _number(_value(source_row, resolved.get("vcpu")))
            if quantity is not None and vcpus is not None and vcpus > 0:
                quantity *= vcpus
                unit = "vCPU-hour"

        usage_available = quantity is not None and quantity >= 0 and bool(unit)
        cost = _number(_value(source_row, resolved["cost"]))
        currency = _value(source_row, resolved["currency"]).upper()
        if cost is not None and cost < 0:
            cost = None
            cost_adjustments += 1
        if cost is not None and not (len(currency) == 3 and currency.isalpha()):
            cost = None
        if not usage_available:
            quantity = None
            unit = ""
            if cost is None:
                skipped += 1
                continue
            cost_only += 1

        rows.append(
            {
                "provider": provider,
                "service": _service(provider, service_name),
                "region": region,
                "usage_quantity": quantity if usage_available else None,
                "usage_unit": unit,
                "period_start": dates[0],
                "period_end": dates[1],
                "cost_amount": cost,
                "currency": currency if cost is not None else None,
                "data_basis": "usage_only" if usage_available else "cost_only",
            }
        )

    if not rows:
        raise CloudExportError("No rows had usable dates, usage, or cost data.")
    normalized = pd.DataFrame(rows, columns=NORMALIZED_COLUMNS)
    warnings = []
    if skipped:
        warnings.append(
            f"Skipped {skipped} export rows without usable dates, region, service, usage, or cost."
        )
    if cost_adjustments:
        warnings.append(
            f"{cost_adjustments} negative-cost adjustment rows were excluded from cost totals; usage is retained when available."
        )
    if cost_only:
        warnings.append(
            f"{cost_only} cost-only rows are retained without inferring emissions from spend."
        )
    return normalized.to_csv(index=False).encode("utf-8"), warnings
