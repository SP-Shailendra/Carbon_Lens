import math
from dataclasses import asdict
from typing import Any, cast
from uuid import uuid4

import pandas as pd

from .data.csv_loader import load_csv
from .data.validation import validate_usage_frame
from .emissions.calculator import estimate_row
from .emissions.factors import REGISTRY_INFO
from .recommendations.rules import select_top_hotspots
from .storage import utc_now


class AnalysisError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def summarize_ranges(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = "|".join(
            (
                row["method"],
                row["accounting_method"] or "unspecified",
                row["provider_methodology"] or "operational_screening",
            )
        )
        group = groups.setdefault(
            key,
            {
                "method": row["method"],
                "accounting_method": row["accounting_method"],
                "provider_methodology": row["provider_methodology"],
                "row_ids": [],
                "low_kg_co2e": 0.0,
                "central_kg_co2e": 0.0,
                "high_kg_co2e": 0.0,
                "range_assumption": "Sum of row scenario endpoints, not a confidence interval. Input scopes may overlap; this is not a deduplicated inventory.",
            },
        )
        group["row_ids"].append(row["row_id"])
        for field in ("low_kg_co2e", "central_kg_co2e", "high_kg_co2e"):
            group[field] += row[field]
            if not math.isfinite(group[field]):
                raise AnalysisError(["Aggregate values exceed the supported numeric range."])
    combined = next(iter(groups.values())) if len(groups) == 1 else None
    return {
        "estimated_kg_co2e": combined["central_kg_co2e"] if combined else None,
        "method": combined["method"] if combined else "not_estimated",
        "low_kg_co2e": combined["low_kg_co2e"] if combined else None,
        "central_kg_co2e": combined["central_kg_co2e"] if combined else None,
        "high_kg_co2e": combined["high_kg_co2e"] if combined else None,
        "range_assumption": combined["range_assumption"]
        if combined
        else "No compatible single total; see method/accounting groups.",
        "totals_by_method": list(groups.values()),
    }


def analyze_usage(file_bytes: bytes, top_n: int = 3) -> dict[str, Any]:
    if not 1 <= top_n <= 3:
        raise AnalysisError(["top_n must be between 1 and 3."])
    try:
        frame = load_csv(file_bytes)
    except (ValueError, UnicodeError, pd.errors.ParserError) as error:
        raise AnalysisError(["Upload a valid UTF-8 CSV with a header row."]) from error
    validation = validate_usage_frame(frame)
    if not validation.valid:
        raise AnalysisError(validation.errors)
    rows = []
    costs: dict[str, float] = {}
    for index, (_, row) in enumerate(frame.iterrows(), start=1):
        estimate = estimate_row(row)
        parsed_cost = pd.to_numeric(cast(Any, row.get("cost_amount")), errors="coerce")
        cost = float(parsed_cost) if pd.notna(parsed_cost) else None
        currency = str(row["currency"]) if cost is not None else None
        if cost is not None:
            currency_key = cast(str, currency)
            costs[currency_key] = costs.get(currency_key, 0) + cost
        rows.append(
            {
                "row_id": index,
                "provider": str(row["provider"]),
                "service": str(row["service"]),
                "region": str(row["region"]),
                "usage_quantity": float(row["usage_quantity"])
                if estimate.method != "provider_reported" and pd.notna(row.get("usage_quantity"))
                else None,
                "usage_unit": str(row["usage_unit"]) if pd.notna(row.get("usage_unit")) else None,
                "data_basis": str(row["data_basis"])
                if pd.notna(row.get("data_basis"))
                else "usage_only",
                "period_start": str(row["period_start"]),
                "period_end": str(row["period_end"]),
                "cost_amount": cost,
                "currency": currency,
                "energy_basis": str(row["energy_basis"])
                if pd.notna(row.get("energy_basis"))
                else None,
                "energy_source": str(row["energy_source"])
                if pd.notna(row.get("energy_source"))
                else None,
                **asdict(estimate),
            }
        )
    estimated = [row for row in rows if row["status"] == "estimated"]
    recommendations = []
    modeled = [row for row in estimated if row["method"] == "estimated_usage"]
    if modeled:
        hotspots = select_top_hotspots(pd.DataFrame(modeled), "central_kg_co2e", top_n)
        for hotspot in hotspots.to_dict(orient="records"):
            service = hotspot["service"].strip().lower()
            allowed_actions = ["review_utilization"]
            if service == "compute":
                allowed_actions.append("review_schedule")
            elif service == "storage":
                allowed_actions.append("review_storage_lifecycle")
            recommendations.append(
                {
                    "id": f"hotspot-{hotspot['row_id']}",
                    "row_id": hotspot["row_id"],
                    "title": f"Review {hotspot['provider']} {hotspot['service']} in {hotspot['region']}",
                    "explanation": (
                        f"Method estimated_usage: central {hotspot['central_kg_co2e']:.6g} kg CO2e, "
                        f"scenario range {hotspot['low_kg_co2e']:.6g} to {hotspot['high_kg_co2e']:.6g}. "
                        "Check utilization and workload requirements "
                        "before considering rightsizing or scheduling changes."
                    ),
                    "estimated_kg_co2e": hotspot["estimated_kg_co2e"],
                    "method": hotspot["method"],
                    "low_kg_co2e": hotspot["low_kg_co2e"],
                    "central_kg_co2e": hotspot["central_kg_co2e"],
                    "high_kg_co2e": hotspot["high_kg_co2e"],
                    "range_assumption": hotspot["range_assumption"],
                    "accounting_method": hotspot["accounting_method"],
                    "provenance": hotspot["provenance"],
                    "decision": "pending",
                    "allowed_actions": allowed_actions,
                    "evidence": [
                        f"Row {hotspot['row_id']}: {hotspot['usage_quantity']:g} {hotspot['usage_unit']} during "
                        f"{hotspot['period_start']} to {hotspot['period_end']}.",
                        f"Estimated emissions use factor {hotspot['factor_id']}; ranking covers supported rows only.",
                        f"Source: {hotspot['factor']['source_url']}",
                    ],
                    "effort": "Small initial investigation; implementation effort depends on findings.",
                    "risks": [
                        "Reducing capacity or changing schedules may affect latency, availability, and recovery objectives.",
                        "Usage totals alone do not establish that a workload is idle or oversized.",
                    ],
                    "next_steps": [
                        "Identify the workload owner and confirm which resources this usage row represents.",
                        "Review utilization, peak demand, and service-level objectives for the same reporting period.",
                        "Propose a reversible change, test it in staging, and define a rollback plan before approval.",
                        "Compare equivalent before-and-after usage; do not interpret this estimate as verified savings.",
                    ],
                    "potential_savings_kg_co2e": None,
                    "savings_reason": "No validated reduction scenario or before-and-after activity data was supplied.",
                }
            )
    ranges = summarize_ranges(estimated)
    if any(not math.isfinite(cost) for cost in costs.values()):
        raise AnalysisError(["Aggregate values exceed the supported numeric range."])
    warnings = list(validation.warnings)
    if modeled:
        warnings.append(
            "Usage estimates are operational screening scenarios using published historical proxies, not current provider measurements or full lifecycle footprints. Ranges do not bound grid, PUE, hardware, temporal or source uncertainty. No modeled savings are implied."
        )
    if len(ranges["totals_by_method"]) > 1:
        warnings.append(
            "Different methods/accounting bases or provider methodology labels are not combined. Review group totals and source scopes; overlapping reported and modeled usage can double-count."
        )
    return {
        "id": str(uuid4()),
        "created_at": utc_now(),
        "methodology_version": "2",
        "registry_version": REGISTRY_INFO.get("registry_version"),
        "summary": {
            "total_rows": len(rows),
            "estimated_rows": len(estimated),
            "not_estimated_rows": len(rows) - len(estimated),
            **ranges,
            "coverage_percent": round(100 * len(estimated) / len(rows), 2) if rows else 0,
            "costs_by_currency": costs,
        },
        "rows": rows,
        "recommendations": recommendations,
        "warnings": warnings,
        "explanation_mode": "deterministic",
        "limitations": [
            "Experimental estimates, not audited carbon accounting.",
            "Totals cover supported rows only; unestimated usage is not zero emissions.",
            "Recommendations require human review and never change cloud infrastructure.",
            "Usage models omit GPU, networking, extra memory, embodied emissions and storage replication. Annual grid/PUE proxies are not current measurements.",
        ],
        "steps": ["validated", "estimated", "ranked", "awaiting_human_review"],
    }
