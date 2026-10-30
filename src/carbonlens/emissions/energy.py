import calendar
from dataclasses import dataclass
from datetime import date

import pandas as pd

from .factors import UsageProfile


@dataclass(frozen=True)
class EnergyRange:
    low: float
    central: float
    high: float
    assumption: str
    formula: str


def estimate_energy(row: pd.Series, profile: UsageProfile) -> EnergyRange:
    # CCF compute/storage/PUE equations and coefficients, accessed 2026-10-27:
    # https://www.cloudcarbonfootprint.org/docs/methodology/
    quantity = float(row["usage_quantity"])
    service = str(row["service"]).strip().lower()
    raw_unit = str(row["usage_unit"]).strip()
    if raw_unit not in {"vCPU-hour", "GB-hour", "TB-hour", "GB-month"}:
        raise ValueError(
            "Usage units are case-sensitive: vCPU-hour, GB-hour, TB-hour, GB-month. Bits, GiB and ambiguous units are not converted."
        )
    unit = str(row["usage_unit"]).strip().lower()
    if service == "compute" and unit == "vcpu-hour":
        low_watts = profile.min_watts
        high_watts = profile.max_watts
        central_watts = low_watts + profile.central_utilization * (high_watts - low_watts)
        scale = quantity / 1000 * profile.pue
        return EnergyRange(
            low_watts * scale,
            central_watts * scale,
            high_watts * scale,
            f"Utilization scenarios: 0%, {100 * profile.central_utilization:g}% central, and 100%, with fixed published fleet-average power/PUE and grid proxy. Not a confidence interval.",
            "vCPU-hours * (min_W + utilization * (max_W - min_W)) / 1000 * PUE * grid_kg_per_kWh",
        )
    if service == "storage" and unit in {"gb-hour", "tb-hour", "gb-month"}:
        tb_hours = quantity if unit == "tb-hour" else quantity / 1000
        if unit == "gb-month":
            start = date.fromisoformat(str(row["period_start"]))
            end = date.fromisoformat(str(row["period_end"]))
            if (
                start.day != 1
                or (start.year, start.month) != (end.year, end.month)
                or end.day != calendar.monthrange(start.year, start.month)[1]
            ):
                raise ValueError(
                    "GB-month requires exactly one complete calendar month; use GB-hour for other periods."
                )
            tb_hours *= end.day * 24
        medium = str(row.get("storage_medium", "unknown")).strip().lower()
        if medium in {"nan", "none", ""}:
            medium = "unknown"
        if medium not in {"unknown", "hdd", "ssd"}:
            raise ValueError("storage_medium must be hdd, ssd, or unknown.")
        hdd, ssd = profile.hdd_wh_per_tb_hour, profile.ssd_wh_per_tb_hour
        low, high = (
            (hdd, ssd) if medium == "unknown" else ((hdd, hdd) if medium == "hdd" else (ssd, ssd))
        )
        low, high = min(low, high), max(low, high)
        scale = tb_hours / 1000 * profile.pue
        return EnergyRange(
            low * scale,
            ((low + high) / 2) * scale,
            high * scale,
            "Storage medium scenarios: HDD low, arithmetic midpoint central, SSD high when unspecified; known medium gives equal endpoints. Decimal GB/TB, actual calendar-month hours, replication excluded. Not a confidence interval.",
            "TB-hours * storage_Wh_per_TB_hour / 1000 * PUE * grid_kg_per_kWh",
        )
    raise ValueError(
        "Unsupported service/unit. Only compute vCPU-hour and storage GB-hour, TB-hour, or single-calendar GB-month are modeled; GPU, network, extra memory and embodied emissions are excluded."
    )
