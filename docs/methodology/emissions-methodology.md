# Emissions Methodology — Draft

> Archived methodology v1. The current calculation contract, sources, scenario ranges and registry format are documented in [Emissions Methodology V2](emissions-methodology-v2.md). The historical EPA reference below is retained for auditability; v1's statements about unsupported usage and single-version registry configuration no longer describe v2.

## Status
One primary-source historical screening reference is bundled for AWS compute in us-east-1 using facility electricity in kWh for data-year 2023. It is not an AWS-specific measurement, market-based footprint, full lifecycle estimate, or audited inventory. Other combinations require documented compatible factors; generic vCPU-hours are not converted into energy.

## Historical AWS electricity reference

Primary source: [US EPA eGRID2023 metric workbook, revision 2](https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_metric_rev2.xlsx), released 12 June 2025, accessed 26 October 2026. The [EPA download page](https://www.epa.gov/egrid/download-data) identifies the data year and revision. The workbook's `NRL23` sheet, `NERC=SERC`, field `NRC2ERTA` is the annual CO2-equivalent total-output emission rate in kg/MWh.

- Source value: **365.1339384 kg CO2e/MWh**.
- Unit conversion: **365.1339384 / 1000 = 0.3651339384 kg CO2e/kWh**.
- Calculation: attributable facility kWh multiplied by 0.3651339384.
- Workbook SHA-256: `3dfbbcf2f949d58d5b2dbee3aab8150bd04a0c8ebb730ba1cd37a013bd4450ab`.
- Region proxy: the mapping of AWS us-east-1 to the broader SERC NERC region follows [Cloud Carbon Footprint methodology](https://www.cloudcarbonfootprint.org/docs/methodology/), Appendix V. This geographic proxy is an assumption, not proof of a particular workload's electricity supply.

The primary metric workbook is authoritative for the numeric value. CCF's published derived figure differs slightly, so it is not substituted for this source value. The workbook was parsed with a structured spreadsheet reader and its field name, units, value, and checksum were checked; no spreadsheet parser is required at runtime.

The profile requires `provider=aws`, `service=compute`, `region=us-east-1`, and `usage_unit=kWh`. `period_start` and `period_end` must fall wholly within 2023. Restricting application to the data year is a conservative CarbonLens policy, not an assertion that EPA guarantees a validity interval. No 2026 factor is implied by a 2026 access date.

Each row must also supply `energy_basis=facility` and a nonempty `energy_source` reference to measurement or a defensible allocation. Facility energy includes cooling and other overhead, so no extra PUE multiplier is applied. IT-only kWh is not supported by this profile. A nonempty evidence reference does not establish its truth; energy attribution still requires human review. Ordinary EC2 billing quantities are not facility kWh and must not be relabeled.

This is an annual location-based generation-output screening estimate. It excludes embodied hardware emissions, upstream fuel emissions, grid losses, and market-based renewable procurement claims. Hourly electricity differences and workload-specific hardware effects are not represented. No scientifically justified numerical uncertainty interval is available, so the application does not invent one. Display precision is not a claim of accuracy.

The synthetic reference sample contains 120, 80, and 40 kWh for separate 2023 months. Its computed 87.632145216 kg CO2e is a reproducible software example, not customer usage or evidence of emissions reductions. Recommendations expose input evidence, operational risks, investigative effort and reversible next steps. Savings remain unknown without a validated reduction scenario.

## Required factor metadata
Factor ID, value, unit, compatible input unit, provider/service/resource category, geography, publication/version date, source organization and URL, assumptions, exclusions, and uncertainty.

## Calculation contract
Conceptually: `estimated emissions = supported activity data × compatible emissions factor`.

The exact formula depends on factor units and methodology. Do not apply generic factors to arbitrary cost, GB, or vCPU-hour values unless the source explicitly supports the conversion.

## Missing data
If activity data, units, region, period, or compatible factor is missing, return “not estimated” with a reason.

## Validation
Compare against a reference tool only when input scope and assumptions are comparable. Document differences.

## Factor configuration

`EMISSION_FACTORS_PATH` names a server-side JSON file containing an array of factor definitions. A configured file replaces the bundled registry. An empty array is valid and disables estimates. Do not place real bills or secrets in this file.

Every object requires the following fields; unknown fields are rejected:

| Field | Contract |
|---|---|
| `factor_id` | Unique nonempty factor identifier |
| `provider` | `aws`, `azure`, or `gcp` |
| `service` | Exact normalized CSV service category |
| `region` | Exact normalized CSV cloud region |
| `input_unit` | Exact CSV usage unit, for example `vCPU-hour` |
| `value` | Finite, nonnegative numeric emission factor from the reviewed source |
| `unit` | Exactly `kgCO2e/<input_unit>` |
| `source_name` | Source organization/publication |
| `source_url` | Valid HTTP or HTTPS source URL |
| `geography` | Applicable geography from the source |
| `valid_from` / `valid_to` | Inclusive ISO dates covering the entire usage period |
| `version` | Source publication version or publication date |
| `notes` | Assumptions, exclusions, and uncertainty |

Optional `required_energy_basis` may be `facility` to require facility-energy inputs and a nonempty `energy_source`; omission preserves the original factor contract. A compatible number and source URL alone do not establish defensible energy attribution.

The compatibility key is `provider|service|region|input_unit`, normalized to lowercase. Duplicate keys and factor IDs are rejected at startup; this MVP supports one configured factor per key, not a time-series registry. The entire row reporting period must fit the factor validity window; partially overlapping rows are not prorated. Quantities are multiplied only by compatible factors, and each result includes the formula, factor value, unit, source, and validity metadata. Non-finite products are marked not estimated; non-finite aggregate totals are rejected.

Configuration validates metadata and unit compatibility, not the source's scientific validity. The bundled numeric reference is primary-source data, not a synthetic factor. Synthetic factors remain confined to tests. Missing factors, dates outside factor validity, incompatible energy basis, and unsupported units, services, or regions never yield fabricated numeric emissions. Totals and rankings cover supported rows only, and are not estimates of the full cloud estate. Cost totals are kept separate by currency and are not converted into emissions.
