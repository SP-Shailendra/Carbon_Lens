import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, model_validator


@dataclass(frozen=True)
class EmissionFactor:
    factor_id: str
    value: float
    unit: str
    source_name: str
    source_url: str
    geography: str
    valid_from: str
    notes: str = ""
    valid_to: str | None = None
    version: str = "unspecified"
    required_energy_basis: str | None = None
    access_date: str | None = None
    method: str = "location_based"
    verified: bool = False
    factor_kind: str = "direct"
    provider: str = ""
    service: str = ""
    region: str = ""
    input_unit: str = ""
    data_year: int | None = None


EMISSION_FACTORS: dict[str, EmissionFactor] = {}
# Published-value provenance checked 2026-10-27; registry dates distinguish source vintage from model applicability.
# https://www.cloudcarbonfootprint.org/docs/methodology/ and https://cloud.google.com/sustainability/region-carbon
# Retained EPA reference: https://www.epa.gov/egrid/download-data (rechecked 2026-10-27).
REGISTRY_PATH = Path(__file__).with_name("registry.json")
REGISTRY_INFO: dict[str, str] = {}


class FactorDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factor_id: str = Field(min_length=1, max_length=100)
    provider: Literal["aws", "azure", "gcp"]
    service: str = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=100)
    input_unit: str = Field(min_length=1, max_length=100)
    value: float = Field(ge=0, allow_inf_nan=False)
    unit: str
    source_name: str = Field(min_length=1)
    source_url: HttpUrl
    geography: str = Field(min_length=1)
    valid_from: date
    valid_to: date
    version: str = Field(min_length=1)
    notes: str = Field(min_length=1)
    required_energy_basis: Literal["facility"] | None = None
    access_date: date | None = None
    method: Literal["location_based", "market_based"] = "location_based"
    verified: bool = False
    factor_kind: Literal["direct", "grid"] = "direct"
    data_year: int | None = None

    @model_validator(mode="after")
    def validate_compatibility(self):
        if self.valid_to < self.valid_from:
            raise ValueError("valid_to must be on or after valid_from")
        if self.unit != f"kgCO2e/{self.input_unit}":
            raise ValueError("unit must be kgCO2e/<input_unit>")
        if any("|" in value for value in (self.service, self.region, self.input_unit)):
            raise ValueError("Factor key fields cannot contain '|'")
        if self.verified and self.access_date is None:
            raise ValueError("Verified factors require an access_date")
        return self


class UsageProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    provider: Literal["aws", "azure", "gcp"]
    min_watts: float = Field(ge=0, allow_inf_nan=False)
    max_watts: float = Field(ge=0, allow_inf_nan=False)
    central_utilization: float = Field(ge=0, le=1, allow_inf_nan=False)
    hdd_wh_per_tb_hour: float = Field(ge=0, allow_inf_nan=False)
    ssd_wh_per_tb_hour: float = Field(ge=0, allow_inf_nan=False)
    pue: float = Field(ge=1, allow_inf_nan=False)
    source_url: HttpUrl
    access_date: date
    valid_from: date
    valid_to: date
    geography: str
    method: Literal["location_based", "market_based"]
    verified: bool
    notes: str

    @model_validator(mode="after")
    def validate_order(self):
        if self.max_watts < self.min_watts or self.valid_to < self.valid_from:
            raise ValueError("Profile bounds must be ordered")
        return self


USAGE_PROFILES: dict[str, UsageProfile] = {}


def load_factor_file(path: str) -> None:
    payload = json.loads(Path(path).read_bytes())
    profiles = []
    version = "legacy-unversioned"
    if isinstance(payload, dict):
        if payload.get("schema_version") != 2 or not payload.get("registry_version"):
            raise ValueError("Registry requires schema_version=2 and a registry_version.")
        version = payload["registry_version"]
        profiles = TypeAdapter(list[UsageProfile]).validate_python(
            payload.get("usage_profiles", [])
        )
        payload = payload["factors"]
    definitions = TypeAdapter(list[FactorDefinition]).validate_python(payload)
    factors: dict[str, EmissionFactor] = {}
    identifiers = set()
    for definition in definitions:
        key = "|".join(
            (definition.provider, definition.service, definition.region, definition.input_unit)
        ).lower()
        if definition.factor_id in identifiers:
            raise ValueError("Factor IDs must be unique.")
        for existing in factors.values():
            if (
                (
                    existing.provider,
                    existing.service,
                    existing.region,
                    existing.input_unit.lower(),
                    existing.method,
                    existing.factor_kind,
                )
                == (
                    definition.provider,
                    definition.service,
                    definition.region,
                    definition.input_unit.lower(),
                    definition.method,
                    definition.factor_kind,
                )
                and (
                    existing.valid_to is None
                    or definition.valid_from.isoformat() <= existing.valid_to
                )
                and definition.valid_to.isoformat() >= existing.valid_from
            ):
                raise ValueError(
                    "Factor windows for the same key and method must be unique and nonoverlapping."
                )
        identifiers.add(definition.factor_id)
        if key in factors:
            key = f"{key}|{definition.factor_id}"
        factors[key] = EmissionFactor(
            factor_id=definition.factor_id,
            value=definition.value,
            unit=definition.unit,
            source_name=definition.source_name,
            source_url=str(definition.source_url),
            geography=definition.geography,
            valid_from=definition.valid_from.isoformat(),
            valid_to=definition.valid_to.isoformat(),
            version=definition.version,
            notes=definition.notes,
            required_energy_basis=definition.required_energy_basis,
            access_date=definition.access_date.isoformat() if definition.access_date else None,
            method=definition.method,
            verified=definition.verified,
            factor_kind=definition.factor_kind,
            provider=definition.provider,
            service=definition.service,
            region=definition.region,
            input_unit=definition.input_unit,
            data_year=definition.data_year,
        )
    if len({profile.provider for profile in profiles}) != len(profiles):
        raise ValueError("Usage profile providers must be unique.")
    EMISSION_FACTORS.clear()
    EMISSION_FACTORS.update(factors)
    USAGE_PROFILES.clear()
    USAGE_PROFILES.update({profile.provider: profile for profile in profiles})
    REGISTRY_INFO.clear()
    REGISTRY_INFO.update({"registry_version": version, "schema_version": "2"})


def matching_factors(
    provider: str, service: str, region: str, unit: str, method: str, kind: str
) -> list[EmissionFactor]:
    matches = []
    for key, factor in EMISSION_FACTORS.items():
        parts = key.split("|")
        if len(parts) < 4:
            continue
        if (parts[0], parts[1], parts[2], parts[3], factor.method, factor.factor_kind) == (
            provider,
            service,
            region,
            unit,
            method,
            kind,
        ):
            matches.append(factor)
    return matches


load_factor_file(str(REGISTRY_PATH))
