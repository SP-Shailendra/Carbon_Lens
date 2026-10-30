import math
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from .energy import estimate_energy
from .factors import REGISTRY_INFO, USAGE_PROFILES, matching_factors


@dataclass(frozen=True)
class EstimateResult:
    status: str
    estimated_kg_co2e: float | None
    factor_id: str | None
    reason: str | None
    method: str = "not_estimated"
    low_kg_co2e: float | None = None
    central_kg_co2e: float | None = None
    high_kg_co2e: float | None = None
    range_assumption: str | None = None
    accounting_method: str | None = None
    provider_methodology: str | None = None
    formula: str | None = None
    provenance: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    factor: dict[str, Any] | None = None
    registry_version: str | None = None


def not_estimated(reason: str) -> EstimateResult:
    return EstimateResult("not_estimated", None, None, reason)


def text(row: pd.Series, name: str, default: str = "") -> str:
    value = row.get(name)
    return default if pd.isna(value) else str(value).strip()


def finish(low: float, central: float, high: float, **metadata: Any) -> EstimateResult:
    if (
        not all(math.isfinite(value) and value >= 0 for value in (low, central, high))
        or not low <= central <= high
    ):
        return not_estimated(
            "Calculation exceeds the supported numeric range or has unordered endpoints."
        )
    return EstimateResult(
        "estimated",
        central,
        metadata.pop("factor_id", None),
        None,
        low_kg_co2e=low,
        central_kg_co2e=central,
        high_kg_co2e=high,
        registry_version=REGISTRY_INFO.get("registry_version"),
        **metadata,
    )


def estimate_row(row: pd.Series) -> EstimateResult:
    basis = text(row, "data_basis", "usage_only").lower()
    if basis == "provider_reported":
        try:
            central = float(row["provider_kg_co2e"])
            low = (
                float(row["provider_low_kg_co2e"])
                if pd.notna(row.get("provider_low_kg_co2e"))
                else central
            )
            high = (
                float(row["provider_high_kg_co2e"])
                if pd.notna(row.get("provider_high_kg_co2e"))
                else central
            )
        except (KeyError, ValueError, TypeError):
            return not_estimated("Provider-reported emissions must be finite numeric kg CO2e.")
        label = text(row, "provider_methodology")
        source = text(row, "provider_source_url")
        access_date = text(row, "provider_access_date")
        if not label or not source or not access_date:
            return not_estimated(
                "Provider figure requires methodology, source URL and access date; it is never recalculated."
            )
        return finish(
            low,
            central,
            high,
            method="provider_reported",
            provider_methodology=label,
            accounting_method=text(row, "accounting_method") or None,
            range_assumption="Provider-supplied endpoints retained; absent endpoints repeat the provider figure and mean uncertainty was not supplied, not zero uncertainty.",
            formula="Provider figure retained unchanged; no energy, PUE or grid calculation.",
            provenance=[
                {
                    "source_url": source,
                    "access_date": access_date,
                    "methodology": label,
                    "verified": False,
                    "verification_note": "User-supplied provider attribution, not independently authenticated.",
                }
            ],
            assumptions=[
                "Provider-reported scope and methodology are retained, not reconciled with modeled operational emissions."
            ],
        )
    if basis != "usage_only":
        return not_estimated("Unknown data_basis; expected usage_only or provider_reported.")
    try:
        start = date.fromisoformat(str(row["period_start"]))
        end = date.fromisoformat(str(row["period_end"]))
        quantity = float(row["usage_quantity"])
    except (ValueError, KeyError, TypeError):
        return not_estimated("Usage requires valid reporting dates and a numeric quantity.")
    if not math.isfinite(quantity) or quantity < 0 or end < start:
        return not_estimated("Usage quantity and reporting period are invalid.")
    provider, service, region, unit = (
        text(row, name).lower() for name in ("provider", "service", "region", "usage_unit")
    )
    accounting = text(row, "accounting_method", "location_based").lower()
    direct = matching_factors(provider, service, region, unit, accounting, "direct")
    if direct:
        applicable = [
            factor
            for factor in direct
            if start.isoformat() >= factor.valid_from
            and (factor.valid_to is None or end.isoformat() <= factor.valid_to)
        ]
        if not applicable:
            return not_estimated("Reporting period is outside factor validity dates.")
        factor = applicable[0]
        if not factor.verified:
            return not_estimated("Compatible factor is unverified and is not used.")
        expected_unit = factor.input_unit or factor.unit.partition("/")[2]
        if text(row, "usage_unit") != expected_unit:
            return not_estimated(
                "Direct-factor input units are case-sensitive and must match exactly."
            )
        if factor.required_energy_basis and (
            text(row, "energy_basis").lower() != factor.required_energy_basis
            or not text(row, "energy_source")
        ):
            return not_estimated(
                "This factor requires energy_basis=facility and a nonempty energy_source reference; facility kWh must already include cooling overhead. IT-only energy is not supported."
            )
        value = quantity * factor.value
        return finish(
            value,
            value,
            value,
            method="estimated_usage",
            factor_id=factor.factor_id,
            accounting_method=factor.method,
            factor=asdict(factor),
            provenance=[asdict(factor)],
            range_assumption="Documented direct factor has no published uncertainty endpoints; equal values are a point-reference scenario, not zero uncertainty.",
            formula="usage_quantity * factor.value",
            assumptions=[factor.notes],
        )
    profile = USAGE_PROFILES.get(provider)
    if profile is None or not profile.verified or accounting != profile.method:
        return not_estimated(
            "No verified compatible usage profile/accounting method is configured."
        )
    if not profile.valid_from <= start <= end <= profile.valid_to:
        return not_estimated("Reporting period is outside usage-profile applicability dates.")
    grids = matching_factors(provider, "*", region, "kwh", accounting, "grid")
    applicable_grids = [
        factor
        for factor in grids
        if factor.verified
        and start.isoformat() >= factor.valid_from
        and factor.valid_to is not None
        and end.isoformat() <= factor.valid_to
    ]
    if not applicable_grids:
        return not_estimated(
            "No verified compatible regional grid factor is configured for the reporting period."
        )
    factor = applicable_grids[0]
    try:
        energy = estimate_energy(row, profile)
    except ValueError as error:
        return not_estimated(str(error))
    return finish(
        energy.low * factor.value,
        energy.central * factor.value,
        energy.high * factor.value,
        method="estimated_usage",
        factor_id=factor.factor_id,
        accounting_method=factor.method,
        factor=asdict(factor),
        provenance=[asdict(factor), profile.model_dump(mode="json")],
        range_assumption=energy.assumption,
        formula=energy.formula,
        assumptions=[
            factor.notes,
            profile.notes,
            "Excludes embodied emissions, networking, GPUs, additional memory, grid losses, upstream fuel emissions and storage replication; storage quantities must be allocated, not merely utilized capacity.",
        ],
    )
