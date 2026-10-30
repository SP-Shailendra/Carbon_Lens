import math
from dataclasses import dataclass
from datetime import date

import pandas as pd
from pydantic import HttpUrl, TypeAdapter, ValidationError

REQUIRED_COLUMNS = {
    "provider",
    "service",
    "region",
    "usage_quantity",
    "usage_unit",
    "period_start",
    "period_end",
}


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]


def validate_usage_frame(frame: pd.DataFrame) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    basis = (
        frame["data_basis"].fillna("usage_only").astype(str).str.strip().str.lower()
        if "data_basis" in frame
        else pd.Series("usage_only", index=frame.index)
    )
    reported = basis.eq("provider_reported")
    usage_only = basis.eq("usage_only")
    cost_only = basis.eq("cost_only")
    required = REQUIRED_COLUMNS - {"usage_quantity", "usage_unit"}
    if usage_only.any():
        required |= {"usage_quantity", "usage_unit"}
    if cost_only.any():
        required |= {"cost_amount", "currency"}
    missing = sorted(required - set(frame.columns))
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")
        return ValidationResult(False, errors, warnings)

    if frame.empty:
        errors.append("CSV must contain at least one usage row.")
    if len(frame) > 50_000:
        errors.append("CSV exceeds the 50,000-row limit.")
    if not basis.isin({"usage_only", "provider_reported", "cost_only"}).all():
        errors.append("data_basis must be usage_only, provider_reported, or cost_only.")
    usage = frame.loc[usage_only]
    numeric = pd.to_numeric(usage.get("usage_quantity", pd.Series(dtype=float)), errors="coerce")
    if not numeric.map(lambda value: pd.notna(value) and math.isfinite(value)).all():
        errors.append("usage_quantity must contain finite numeric values.")
    elif (numeric < 0).any():
        errors.append("usage_quantity cannot be negative.")
    base_required = REQUIRED_COLUMNS - {"usage_quantity", "usage_unit"}
    if frame[list(base_required)].isna().any().any() or any(
        frame[column].astype(str).str.strip().eq("").any() for column in base_required
    ):
        errors.append("Required fields cannot be blank.")
    for column in ("usage_quantity", "usage_unit"):
        if column in usage and (
            usage[column].isna().any() or usage[column].astype(str).str.strip().eq("").any()
        ):
            errors.append(f"{column} cannot be blank for usage-only rows.")
    if "accounting_method" in frame:
        methods = frame["accounting_method"].dropna().astype(str).str.strip()
        if not methods.isin({"location_based", "market_based"}).all():
            errors.append("accounting_method must be location_based or market_based when supplied.")
    for position, (_, row) in enumerate(frame.iterrows(), start=2):
        if not reported.iloc[position - 2]:
            continue
        prefix = f"CSV row {position}: "
        try:
            value = float(row["provider_kg_co2e"])
            if not math.isfinite(value) or value < 0:
                raise ValueError()
        except (KeyError, ValueError, TypeError):
            errors.append(prefix + "provider_kg_co2e must be finite nonnegative kg CO2e.")
            continue
        if (
            pd.isna(row.get("provider_methodology"))
            or not str(row.get("provider_methodology", "")).strip()
        ):
            errors.append(
                prefix + "provider_methodology is required for provider-reported figures."
            )
        try:
            TypeAdapter(HttpUrl).validate_python(row.get("provider_source_url"))
            date.fromisoformat(str(row.get("provider_access_date")))
        except (ValidationError, ValueError, TypeError):
            errors.append(prefix + "provider_source_url and ISO provider_access_date are required.")
        bounds_supplied = [
            pd.notna(row.get(column))
            for column in ("provider_low_kg_co2e", "provider_high_kg_co2e")
        ]
        if any(bounds_supplied):
            try:
                low, high = float(row["provider_low_kg_co2e"]), float(row["provider_high_kg_co2e"])
                if (
                    not all(bounds_supplied)
                    or not math.isfinite(low)
                    or not math.isfinite(high)
                    or not 0 <= low <= value <= high
                ):
                    raise ValueError()
            except (KeyError, ValueError, TypeError):
                errors.append(
                    prefix
                    + "Provider bounds must both be supplied and satisfy 0 <= low <= provider figure <= high."
                )
    providers = frame["provider"].astype(str).str.strip().str.lower()
    if not providers.isin({"aws", "azure", "gcp"}).all():
        errors.append("provider must be aws, azure, or gcp.")
    dates = {}
    for column in ("period_start", "period_end"):
        text = frame[column].astype(str)
        dates[column] = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
        if dates[column].isna().any() or not text.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
            errors.append(f"{column} must contain valid YYYY-MM-DD dates.")
    if (dates["period_end"] < dates["period_start"]).any():
        errors.append("period_end must be on or after period_start.")

    if "cost_amount" in frame.columns:
        cost = pd.to_numeric(frame["cost_amount"], errors="coerce")
        supplied = frame["cost_amount"].notna() & frame["cost_amount"].astype(str).str.strip().ne(
            ""
        )
        if not cost[supplied].map(lambda value: pd.notna(value) and math.isfinite(value)).all():
            errors.append("cost_amount must be finite and numeric when provided.")
        elif (cost[supplied] < 0).any():
            errors.append("cost_amount cannot be negative.")
        if supplied.any():
            if "currency" not in frame.columns:
                errors.append("currency is required when cost_amount is provided.")
            elif (
                not frame.loc[supplied, "currency"]
                .fillna("")
                .astype(str)
                .str.fullmatch(r"[A-Z]{3}")
                .all()
            ):
                errors.append(
                    "currency must be a three-letter uppercase code when cost_amount is provided."
                )
        if cost_only.any() and not supplied[cost_only].all():
            errors.append("cost_only rows require a cost_amount and currency.")

    if cost_only.any():
        warnings.append("Cost-only rows are retained but emissions are not inferred from spend.")

    return ValidationResult(not errors, errors, warnings)
