# Emissions Methodology V2

Registry version: `2026.10.27`. Source review date: **2026-10-27**. This is an experimental operational screening model, not an audited inventory, provider report reproduction, full Cloud Carbon Footprint implementation, confidence interval, or verified savings calculation.

## Result Contract

Every emission row returns `method`, `low_kg_co2e`, `central_kg_co2e`, `high_kg_co2e`, `range_assumption`, `accounting_method`, `provenance`, `assumptions`, and a reason if unsupported. `estimated_kg_co2e` remains a compatibility alias for central. No rounding changes stored provider figures. Source metadata and formulas travel with JSON and CSV; CSV embeds structured provenance as JSON text and escapes spreadsheet-formula prefixes.

- `provider_reported`: a supplied provider figure, never multiplied by energy coefficients, PUE, or grid factors. Provider attribution is user-supplied, not independently authenticated.
- `estimated_usage`: a deterministic modeled scenario or the retained direct-energy reference, with documented inputs and exclusions.
- `not_estimated`: all emission bounds and the compatibility value are null, with an explicit refusal reason. Unsupported usage is not zero emissions.

Provider-reported and modeled totals are separated. Location-based and market-based accounting are separated. Different provider methodology labels are separated. A single summary number is returned only for one compatible group; otherwise inspect `totals_by_method`. Group totals reference their input row IDs. These are sums of input scenarios, not a deduplicated inventory: even similarly labeled rows may overlap or have incompatible lifecycle scopes. No automatic provider-versus-model substitution is performed.

## Versioned Registry

The packaged JSON registry is `src/carbonlens/emissions/registry.json`. It has `schema_version=2`, `registry_version`, `factors`, and `usage_profiles`. Factor records include source name/URL, access date, geography, version, application dates, method (`location_based` or `market_based`), `verified`, compatible provider/service/region/unit, value/unit, and notes. Profiles include the power, storage and PUE coefficients with the same source/date/geography/method/verification controls.

`verified=true` means the bundled numeric value was checked against its cited publication. **It does not mean that a workload was measured, that a source is scientifically exact, or that a historical factor is verified for 2026 conditions.** Input metadata and provenance claims are not authenticated. Unverified records are never used. Missing or incompatible grid/profile records produce no estimate, not a global-average fallback.

Multiple dated factor versions may coexist, but their application windows cannot overlap for the same provider/service/region/unit/kind/accounting method. IDs must be unique. Invalid files are rejected before replacing active records. `EMISSION_FACTORS_PATH` replaces both factors and usage profiles with a configured registry; a legacy array remains readable but missing verification/access metadata leaves records unusable, and `[]` disables modeled estimates. Provider figures remain independent of registry configuration.

## Sources and Transcriptions

All URLs below were accessed **2026-10-27**, except the retained primary EPA workbook whose original verified access date remains **2026-10-26**. EPA's current download page was rechecked on 2026-10-27. No native cloud-provider export schema was introduced or inferred.

| Source | URL | Used For |
|---|---|---|
| Cloud Carbon Footprint, Compute/Storage/PUE sections and Appendices I/V | https://www.cloudcarbonfootprint.org/docs/methodology/ | Equations, generic power coefficients, HDD/SSD coefficients, published PUE assumptions, AWS/Azure geographic grid proxies |
| US EPA eGRID download page | https://www.epa.gov/egrid/download-data | Confirms eGRID2023 metric revision 2, dated 2025-06-12 |
| US EPA eGRID2023 metric revision 2 | https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_metric_rev2.xlsx | Retained direct-energy reference: NRL23, SERC, NRC2ERTA, 365.1339384 kg/MWh |
| Google Cloud regional carbon data, 2025 data, page updated 2026-10-26 | https://cloud.google.com/sustainability/region-carbon | Iowa, Mumbai and Delhi gross operational grid intensities; no CFE-percentage discount |
| Google Cloud Carbon Footprint methodology | https://docs.cloud.google.com/carbon-footprint/docs/methodology | Scope/accounting distinctions and why provider figures are passed through rather than reconstructed |

CCF is an open-source methodology publication, not primary per-workload telemetry. Its references to EPA, SPECpower, the US Data Center Energy Usage Report, Microsoft statements and other work are not independently revalidated here. Google describes Electricity Maps as the source of the regional grid data. Source-vintage and source-conflict limits remain visible in each record. Numeric coefficients are factual transcriptions; third-party source content retains its own terms (CCF Apache-2.0; Google documentation CC BY 4.0 unless otherwise noted).

### Usage Coefficients

| Provider | Minimum W/vCPU | Maximum W/vCPU | Central Utilization | PUE Used |
|---|---:|---:|---:|---:|
| AWS | 0.74 | 3.5 | 0.5 | 1.135 |
| Azure | 0.78 | 3.76 | 0.5 | 1.185 |
| GCP | 0.71 | 4.26 | 0.5 | 1.1 |

All values are from CCF's cited public methodology. AWS/GCP values agree between the relevant sections and Appendix I. Azure's main PUE section states **1.185**, while Appendix I states **1.125**. V2 deliberately uses the explicit main PUE section value, records the unresolved conflict, and does not invent an uncertainty distribution from it. These are historical generic CCF fleet assumptions, not contemporary data-center measurements. Profile application windows run 2020-2026 as a versioned **model policy**, not a claim that hardware/PUE stayed constant or was measured for every year.

Storage uses CCF's **0.65 Wh/TB-hour for HDD** and **1.2 Wh/TB-hour for SSD**. Decimal units are explicit: 1000 GB = 1 TB, 1000 Wh = 1 kWh. These are unit definitions, not empirical coefficients. GiB, bits and other dimensions are not silently converted. Storage quantities are assumed allocated capacity, not merely utilized bytes; this assumption must be reviewed.

### Grid Records

| Application | Published Value | Stored kg CO2e/kWh | Data Vintage | Application Window |
|---|---:|---:|---|---|
| Retained AWS compute us-east-1 direct facility kWh | EPA 365.1339384 kg/MWh | 0.3651339384 | 2023 | 2023 only |
| AWS us-east-1 usage model | CCF 0.000365127796 metric tons/kWh | 0.365127796 | CCF cites eGRID2023 | 2023-2026 |
| Azure eastus usage model | CCF East US 0.000379069 metric tons/kWh | 0.379069 | Not specified in CCF's Azure table | 2023-2026 |
| GCP us-central1 / Iowa | Google 432 gCO2eq/kWh | 0.432 | 2025 | 2025-2026 |
| GCP asia-south1 / Mumbai | Google 598 gCO2eq/kWh | 0.598 | 2025 | 2025-2026 |
| GCP asia-south2 / Delhi | Google 473 gCO2eq/kWh | 0.473 | 2025 | 2025-2026 |

CCF's AWS factor is a slightly different published derived figure from the retained primary EPA workbook value. V2 preserves each with its own ID/source rather than silently replacing either. Azure `eastus` is the normalized regional alias for CCF's East US / Virginia / SERC entry, not a native export schema.

Applying historical annual grid values to 2026 activity is an explicit **latest-published proxy scenario**. It is not verification of current-year grid intensity. The Azure source's unspecified underlying data vintage remains unspecified. Applications outside each record's window are refused; no future extrapolation is automatic. Geographic, temporal, grid, hardware, and PUE errors are **not bounded** by the scenario range. AWS and Azure India grid factors remain unconfigured/unverified in this release; GCP's India factors are not transferable across providers or arbitrary regions.

## Compute Scenarios

Accepted normalized combination: `service=compute`, `usage_unit=vCPU-hour` (case-sensitive), with a configured provider profile and regional grid record. Quantities must already be normalized vCPU-hours, not instance-hours; vCPU counts are never guessed from provider names or costs.

```text
average_W = min_W + utilization * (max_W - min_W)
facility_kWh = vCPU_hours * average_W / 1000 * PUE
kg_CO2e = facility_kWh * grid_kg_per_kWh
```

Low/central/high use utilization **0 / 0.5 / 1** with fixed published coefficients, PUE and grid factor. The endpoints are idle/full-load model scenarios; they are not confidence limits or guaranteed bounds on actual emissions. Unknown hardware, additional memory, hourly carbon variation and changing grid conditions remain unquantified.

Hand-worked golden example, AWS us-east-1, 1000 vCPU-hours:

```text
low     = 1000 * 0.74 / 1000 * 1.135 * 0.365127796 = 0.3066708358604 kg CO2e
central = 1000 * 2.12 / 1000 * 1.135 * 0.365127796 = 0.8785705027352 kg CO2e
high    = 1000 * 3.50 / 1000 * 1.135 * 0.365127796 = 1.45047016961 kg CO2e
```

## Storage Scenarios

Accepted normalized combination: `service=storage` and `GB-hour`, `TB-hour`, or `GB-month`, case-sensitive. `GB-month` requires exactly one full calendar month with inclusive start/end dates; month length is calculated from those dates. Partial or multi-month periods must be supplied as GB-hours/TB-hours. No fixed 730-hour month is invented.

```text
TB_hours = GB_hours / 1000
TB_hours_for_one_calendar_GB_month = GB_months / 1000 * calendar_days * 24
facility_kWh = TB_hours * storage_Wh_per_TB_hour / 1000 * PUE
kg_CO2e = facility_kWh * grid_kg_per_kWh
```

With `storage_medium` absent/`unknown`, low uses HDD 0.65, high uses SSD 1.2, and central uses their arithmetic midpoint **0.925**. The midpoint is a CarbonLens scenario assumption, not a measured storage mix or a separately published coefficient. With `hdd` or `ssd`, endpoints coincide and explicitly do not claim zero uncertainty. Replication is excluded; no number of replicas is guessed. Managed services whose underlying resources exceed the normalized storage allocation are outside the modeled boundary.

Hand-worked Azure eastus golden example: 250 GB-month in October (744 hours):

```text
TB_hours = 250 / 1000 * 744 = 186
central = 186 * 0.925 / 1000 * 1.185 * 0.379069 = 0.07728430341825 kg CO2e
```

## Provider-Reported Figures

`data_basis=provider_reported` requires `provider_kg_co2e`, nonempty `provider_methodology`, HTTP(S) `provider_source_url`, and ISO `provider_access_date`. Provider rows need provider/service/region/reporting dates but not usage quantity/unit. These are CarbonLens normalized fields, **not claims about AWS, Azure or Google native CSV schemas**. A caller must normalize an authorized provider report separately.

The central figure is retained unchanged. If both `provider_low_kg_co2e` and `provider_high_kg_co2e` are provided, they must bracket central and are retained unchanged too. Otherwise low/central/high repeat the provider figure and say the provider did not supply uncertainty bounds. This is not a fabricated statistical interval or a claim of zero uncertainty. Negative, nonfinite, unordered, incomplete or unprovenanced figures fail validation; they never fall back to usage modeling.

`provider_methodology` is retained as a label. Optional `accounting_method` is `location_based` or `market_based`; omission remains unspecified for provider figures, never guessed. Provider figures can include scopes absent from the model. V2 does not reconcile them, discount them, infer procurement claims, or generate modeled optimization recommendations from them. The user-provided attribution is marked unverified, independently of registry verification flags.

## Direct Energy and Exclusions

The original EPA entry remains unchanged for AWS compute us-east-1, facility `kWh`, reporting wholly in 2023, with `energy_basis=facility` and `energy_source`. Facility energy includes overhead: **PUE is not applied twice**. Direct-reference endpoints coincide because no uncertainty bounds are configured; this is labeled a point-reference scenario. Missing inputs or incompatible years still yield no estimate.

The usage model excludes GPU workloads, networking, additional memory, embodied equipment/building emissions, upstream fuel emissions, transmission losses and storage replication. It does not derive energy from money, guess a region, parse native billing schemas, estimate savings, or alter infrastructure. Approvals remain records only. AI only labels already-computed recommendations and cannot alter central values, endpoints, assumptions or source records.

## Verification

Golden tests cover hand-derived compute/storage calculations, original EPA arithmetic, Google regional conversions and provider pass-through. Hypothesis checks monotonicity, range ordering, unit equivalence and incompatible-unit refusal. Regression tests cover missing/unverified factors, accounting/date mismatches, malformed provider figures, complete-month requirements, registry version windows, persisted reports, CSV provenance and Streamlit approval controls.

The original unmodified mixed sample reaches 3/3 **row coverage** under these disclosed operational scenarios, not coverage of all cloud/lifecycle emissions. Legacy saved point reports stay stored but return a reanalysis-required response rather than being relabeled with invented ranges.