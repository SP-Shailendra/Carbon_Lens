# Data directory

Only synthetic, public, or explicitly authorized data belongs here. Never commit real cloud bills, credentials, customer identifiers, or employer-confidential data.

## Normalized CSV schema
Required: `provider`, `service`, `region`, `usage_quantity`, `usage_unit`, `period_start`, `period_end`.
Optional: `cost_amount`; `currency` is required when cost is provided.

Usage units must be compatible with a documented emissions factor. If no compatible factor exists, the row must not be estimated.

Both sample files contain synthetic activity and are for development/testing only. No real cloud bills are included.

- `sample_cloud_usage.csv`: unchanged mixed-provider normalized usage. All three rows are covered by methodology-v2 operational screening scenarios using cited historical regional proxies, with explicit model boundaries and low/central/high values. This is row coverage, not full lifecycle coverage.
- `sample_aws_electricity_2023.csv`: synthetic AWS compute facility-electricity allocations in us-east-1 during 2023, compatible with the documented EPA eGRID2023 reference. The activity is synthetic; the emission factor is primary-source data, not a made-up demonstration coefficient.

The electricity profile additionally requires `energy_basis=facility` and a nonempty `energy_source` evidence reference. Facility kWh includes cooling overhead. Do not rename vCPU-hours or IT-only energy as facility kWh. See [the methodology](../docs/methodology/emissions-methodology.md) for source verification and limitations.

V2 retains the original required columns for usage rows. Optional `data_basis` defaults to `usage_only`; `accounting_method` defaults to `location_based` for usage only. Optional `storage_medium` is `hdd`, `ssd` or `unknown`. Storage units are case-sensitive decimal `GB-hour`, `TB-hour`, or `GB-month`; the monthly unit requires one complete calendar month. Bits, GiB, instance-hours and unknown conversions are not guessed.

For `data_basis=provider_reported`, supply provider/service/region/reporting dates, `provider_kg_co2e`, `provider_methodology`, `provider_source_url`, and `provider_access_date`. Usage quantity/unit are unnecessary and are never used to recalculate the provider figure. Optional provider low/high bounds must both be supplied and bracket central; absent bounds explicitly mean uncertainty is unspecified. These are CarbonLens normalized columns, not a provider export schema. See [methodology v2](../docs/methodology/emissions-methodology-v2.md) for the full contract and source list.
