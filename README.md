# CarbonLens 🌱

**Turn cloud usage data into explainable carbon insights and human-approved recommendations.**

CarbonLens is a single-user MVP for startup engineering teams. Users upload a supported cloud-usage CSV, review transparent rule-based emissions estimates, and receive AI-assisted explanations and recommendations they can approve or reject. The software is proprietary; see [LICENSE](LICENSE).

> **Status:** Runnable single-user MVP with methodology-v2 provider pass-through and ranged compute/storage screening estimates. The unchanged mixed sample has three covered rows using cited CCF assumptions and annual grid proxies; this is not full lifecycle coverage or measured impact. The original 2023 EPA facility-electricity reference remains available. See [methodology v2](docs/methodology/emissions-methodology-v2.md) for all sources and limitations.

## Problem
Cloud bills show resource usage and cost, but do not always make it easy to identify emissions hotspots or prioritize practical sustainability actions. CarbonLens aims to connect emissions visibility with explainable, prioritized decisions.

## MVP goals
- Accept a documented CSV format using public or synthetic sample data.
- Validate columns and flag missing or unsupported data.
- Calculate estimates using deterministic formulas and documented emission factors.
- Explain the top three supported hotspots with an LLM.
- Allow users to approve or reject recommendations; never change cloud resources automatically.
- Track the core product funnel with privacy-conscious analytics.
- Document assumptions, uncertainty, and limitations.

## Out of scope
- Direct cloud billing/API integrations.
- Automatic infrastructure changes.
- Carbon offsets or carbon-credit purchasing.
- Multi-team administration and enterprise access controls.
- Regulatory compliance certification or audited carbon accounting.

## Proposed user journey
1. User reviews the data and estimation limitations.
2. User uploads a supported CSV.
3. CarbonLens validates the file and reports unsupported or missing fields.
4. The calculation layer estimates emissions only where inputs and methodology support it.
5. The results view presents the top three estimated hotspots, assumptions, and sources.
6. AI explains the results and suggests candidate actions.
7. The user approves or rejects each recommendation.
8. Product events measure workflow completion and onboarding friction.

## Stack
- Python 3.11+, FastAPI, Streamlit, pandas, Pydantic; CI covers Python 3.11 and 3.12
- Deterministic agent: validate, estimate, rank, explain, await human review
- Optional OpenAI action labeling; deterministic explanations remain authoritative
- SQLite for reports, human decisions, and privacy-minimized local funnel events
- pytest for automated tests, Ruff for lint/format checks, mypy for static type checking

## Repository structure

```text
carbonlens/
├── .github/workflows/ci.yml
├── .streamlit/config.toml
├── .gitattributes
├── .dockerignore
├── app.py
├── README.md
├── LICENSE
├── CHANGELOG.md
├── CONTRIBUTING.md
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
├── compose.yaml
├── .env.example
├── .gitignore
├── data/
│   ├── README.md
│   ├── sample_cloud_usage.csv
│   └── sample_aws_electricity_2023.csv
├── docs/
│   ├── product/
│   │   ├── problem-statement.md
│   │   ├── prd.md
│   │   ├── user-stories.md
│   │   └── metrics-plan.md
│   ├── research/
│   │   ├── secondary-research.md
│   │   └── competitor-analysis.md
│   └── methodology/
│       ├── emissions-methodology.md
│       ├── emissions-methodology-v2.md
│       └── assumptions-and-limitations.md
├── src/carbonlens/
│   ├── __init__.py
│   ├── config.py
│   ├── agent.py
│   ├── api.py
│   ├── storage.py
│   ├── data/
│   │   ├── __init__.py
│   │   ├── csv_loader.py
│   │   ├── export.py
│   │   └── validation.py
│   ├── emissions/
│   │   ├── __init__.py
│   │   ├── factors.py
│   │   ├── registry.json
│   │   ├── energy.py
│   │   └── calculator.py
│   ├── recommendations/
│   │   ├── __init__.py
│   │   ├── rules.py
│   │   └── llm_explainer.py
│   ├── analytics/events.py
│   └── models/schemas.py
└── tests/
    ├── conftest.py
    ├── test_agent.py
    ├── test_api.py
    ├── test_csv_validation.py
    ├── test_emissions_calculator.py
    ├── test_estimation_v2.py
    ├── test_recommendations.py
    └── test_repository.py
```

## Getting started

### 1. Requirements
Python 3.11 is the minimum; Python 3.11 and 3.12 are exercised in CI. Run all commands from the repository root. This is a checkout-based application: the dashboard, sample data, and configuration live alongside the Python package.

### 2. Create a virtual environment

**Windows PowerShell**
```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux**
```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies
For running the application only:
```bash
python -m pip install -r requirements.txt
```

For development and all quality gates, use this instead:
```bash
python -m pip install -r requirements-dev.txt
```

Runtime dependencies are pinned in [requirements.txt](requirements.txt) and used by the package metadata. [requirements-dev.txt](requirements-dev.txt) installs the editable project with the pinned `dev` extra from [pyproject.toml](pyproject.toml): pytest, Hypothesis, Ruff, mypy, and pandas stubs matched to pandas 2.3. All direct runtime/dev dependencies and the build backend have exact version pins; transitive dependencies are not a full hashed lockfile.

### 4. Configure environment
```bash
cp .env.example .env
```
On Windows PowerShell: `Copy-Item .env.example .env`.

Never commit `.env`, API keys, real cloud bills, or confidential customer data.

### 5. Start the FastAPI backend
Run from the repository root:
```bash
python -m uvicorn carbonlens.api:app --app-dir src --host 127.0.0.1 --port 8001
```

### 6. Start the dashboard in another terminal
```bash
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

- Dashboard: http://127.0.0.1:8501
- Interactive API reference: http://127.0.0.1:8001/docs
- API health: http://127.0.0.1:8001/health

Choose **Mixed usage** and **Analyze sample** for three sourced operational screening scenarios with low/central/high values. Choose **AWS electricity (2023)** for the retained point-reference scenario: synthetic 240 facility kWh produces equal low/central/high values of 87.632145216 kg CO2e, explicitly indicating that uncertainty endpoints are unavailable, not zero uncertainty. Both sample types are labeled synthetic in saved reports. A matching header-only CSV template is available before analysis.

The dashboard shows estimation coverage, costs by currency, missing-factor reasons, source metadata, evidence-backed recommendations, effort, operational risks, next steps, approval/rejection, saved reports, and JSON/CSV downloads. Potential savings remain unknown without validated reduction scenarios. Approval never executes cloud changes.

The API is required; the dashboard does not silently bypass it. If changing the API port, update `CARBONLENS_API_URL` and `CARBONLENS_PUBLIC_API_URL` too.

## Runtime parameters

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | Set `production` to require an API key at startup |
| `CARBONLENS_API_KEY` | Empty | Shared single-user API key; sent in `X-API-Key` |
| `CARBONLENS_API_URL` | `http://127.0.0.1:8001` | Backend URL used by the dashboard server |
| `CARBONLENS_PUBLIC_API_URL` | API URL | Browser-accessible API documentation URL |
| `DATABASE_PATH` | `.local/carbonlens.db` | SQLite report, decision, and local event storage |
| `MAX_UPLOAD_MB` | `10` | API and dashboard upload limit, 1-100 MB; 50,000 rows maximum |
| `EMISSION_FACTORS_PATH` | Empty | Server-side reviewed factor JSON file |
| `LLM_PROVIDER` | Empty | Set `openai` to enable optional labeling |
| `LLM_API_KEY` | Empty | Server-side OpenAI credential; never entered in the dashboard |
| `LLM_MODEL` | `gpt-4o-mini` | Model supporting JSON-object responses |

`.env` is loaded without overriding existing environment variables. Keep it private. LLM calls occur only when `use_ai=true` and there are supported recommendations. Only generated hotspot IDs, computed emissions, and fixed allowed-action labels are transmitted, not raw CSV data, service names, identifiers, or costs. Unavailable or invalid AI output falls back to deterministic explanations with a warning. Live provider calls require your credentials and were not needed for local tests.

## API contract

All `/api/v1` routes require `X-API-Key` when a key is configured. `/health`, `/docs`, and `/openapi.json` expose no stored reports and remain public.

| Method | Route | Parameters |
|---|---|---|
| `GET` | `/health` | Liveness |
| `GET` | `/api/v1/config` | Limits, providers, configured factor count, AI availability |
| `GET` | `/api/v1/factors` | Factor metadata and compatibility keys |
| `GET` | `/api/v1/registry` | Registry version, source dates, verified flags, accounting methods and usage coefficients |
| `POST` | `/api/v1/analyses` | Multipart `file` (.csv); query `top_n=1..3`, `use_ai=false` |
| `POST` | `/api/v1/analyses/sample` | Same query parameters; `profile=mixed` (API default) or `profile=aws-electricity-2023` |
| `GET` | `/api/v1/analyses` | Query `limit=1..100`, default 20 |
| `GET` | `/api/v1/analyses/{report_id}` | UUID report identifier |
| `GET` | `/api/v1/analyses/{report_id}/csv` | CSV containing methods, bounds, range assumptions and structured provenance |
| `POST` | `/api/v1/analyses/{report_id}/decisions` | JSON `recommendation_id`, `decision`: `approved` or `rejected` |
| `POST` | `/api/v1/events` | JSON `name`: `onboarding_started` or `report_viewed`; the latter requires `report_id` |

Repeated identical decisions do not create duplicate decision events. Decisions can be revised; timestamps and local events record the change. Invalid data returns 422 with actionable errors, oversized uploads return 413, non-CSV uploads return 415, and unknown reports/recommendations return 404. OpenAPI documents the request and result schemas.

## Configure reviewed factors

The versioned [JSON registry](src/carbonlens/emissions/registry.json) contains the original EPA direct-energy reference, cited CCF compute/storage/PUE assumptions, narrowly mapped AWS/Azure grid proxies, and Google-published 2025 grid factors for Iowa, Mumbai and Delhi. Verification means a checked source transcription, not certification of actual reporting-year conditions. Historical proxy application and the CCF Azure PUE source conflict are disclosed, not hidden inside error bars. AWS/Azure India factors remain unconfigured. No CFE percentage is used to invent a market-based factor.

Set `EMISSION_FACTORS_PATH` to a schema-version-2 registry JSON, then restart the API. It replaces both factor and usage-profile registries. A legacy factor array is still readable, but unverified records are never used; `[]` disables modeled estimates without preventing provider pass-through. Dated factor versions must not overlap for the same key/accounting method. See [methodology v2](docs/methodology/emissions-methodology-v2.md) for exact metadata, units, source URLs/access dates, formulas, scenario definitions and exclusions.

For `data_basis=provider_reported`, the supplied `provider_kg_co2e` is retained unchanged with its `provider_methodology`, `provider_source_url`, and `provider_access_date`. Optional low/high provider values are retained; without them endpoints repeat central with an explicit no-uncertainty-data warning. Provider data is never recalculated or automatically reconciled with modeled activity, and its user-supplied attribution remains unverified.

Rows, recommendations, summaries and CSVs expose `method`, `low_kg_co2e`, `central_kg_co2e`, `high_kg_co2e`, and `range_assumption`. `estimated_kg_co2e` remains a compatibility alias for central. Incompatible methods/accounting bases/provider labels have separate `totals_by_method`; no combined number is claimed. Legacy stored point reports return 409 with a reanalysis request rather than invented ranges; their stored data is not changed.

## Container deployment

```bash
docker compose up --build -d
```

This starts both services on localhost with a persistent `reports` volume. `docker compose down` stops them without deleting reports. A factor file must be copied into the image before building or mounted read-only into the API container, and `EMISSION_FACTORS_PATH` must name its container path.

The default image target is `runtime` and does not install development tools. To reproduce the quality checks in a fresh Linux environment without starting services:

```bash
docker build --target checks --build-arg PYTHON_VERSION=3.11 -t carbonlens-checks:3.11 .
docker build --target checks --build-arg PYTHON_VERSION=3.12 -t carbonlens-checks:3.12 .
```

For an internet-facing deployment, use your hosting provider or a TLS reverse proxy with dashboard authentication, request-size limits, rate limits, and restricted API ingress. Set `APP_ENV=production` and a strong `CARBONLENS_API_KEY` in server secrets. Do not publish the unauthenticated Streamlit port directly: it holds the shared API credential server-side and grants access to the single-user workspace. This MVP does not isolate multiple tenants. Configure persistent storage, retention/backups, and access controls for stored usage data. Hosting accounts, a domain, and cloud deployment credentials are not included in this repository.

## Input CSV contract
The MVP starts with one normalized CSV schema rather than claiming support for every native provider export.

| Column | Meaning | Required |
|---|---|---|
| `provider` | `aws`, `azure`, or `gcp` | Yes |
| `service` | Cloud service/resource category | Yes |
| `region` | Cloud region identifier | Yes |
| `usage_quantity` | Numeric usage quantity | Yes |
| `usage_unit` | Unit for usage quantity | Yes |
| `period_start` | Usage period start | Yes |
| `period_end` | Usage period end | Yes |
| `cost_amount` | Cost amount if available | No |
| `currency` | Currency for cost | If cost provided |
| `energy_basis` | `facility`: energy including cooling overhead | For bundled electricity reference |
| `energy_source` | Nonempty reference to energy measurement/allocation evidence | For bundled electricity reference |
| `data_basis` | `usage_only` (default) or `provider_reported` | No |
| `accounting_method` | `location_based` or `market_based`; unspecified remains unspecified for provider data | No |
| `storage_medium` | `hdd`, `ssd` or `unknown` | No |
| `provider_kg_co2e` | Provider figure in kg CO2e, never recalculated | Provider-reported rows |
| `provider_methodology` | Provider's methodology label, retained as supplied | Provider-reported rows |
| `provider_source_url` / `provider_access_date` | HTTP(S) evidence URL / ISO access date | Provider-reported rows |
| `provider_low_kg_co2e` / `provider_high_kg_co2e` | Optional provider-supplied bounds bracketing central; supply both or neither | No |

Provider-reported rows need provider/service/region/reporting dates but do not require usage quantity/unit. These are CarbonLens normalized fields, not native export schemas. Usage compute requires case-sensitive `vCPU-hour`; storage accepts decimal `GB-hour`, `TB-hour`, or one-complete-calendar-month `GB-month`. Bits, GiB, instance-hours, GPUs, network, embodied emissions and unconfigured regions are not guessed.

Units must match the selected emission factor. Do not multiply arbitrary usage quantities by a generic factor. Unsupported services, missing regions, or incompatible units must be flagged rather than guessed.

## Emissions and AI safety principles
1. Calculations are deterministic and tested in Python, not generated by an LLM.
2. Each factor must include value, unit, source URL, version/date, geography, and applicable resource type.
3. All results are labelled estimates with assumptions and limitations.
4. Missing data or factors result in “not estimated,” with a reason.
5. AI summarizes computed results and suggests actions; it cannot invent numbers or execute changes.
6. Human approval records a decision only; it does not modify cloud infrastructure.
7. Uploaded files are untrusted data, not instructions to the LLM.
8. Do not send raw bills or unnecessary identifiers to analytics or an LLM provider.

## Product analytics
Local, privacy-minimized funnel events:
- `onboarding_started`
- `upload_submitted`
- `upload_validated`
- `report_viewed`
- `recommendation_approved`
- `recommendation_rejected`

**North Star metric:** Percentage of new users who obtain an approved top-three recommendation list within 10 minutes of starting the workflow.

Define the denominator, time window, and treatment of repeat users before reporting. Never fabricate results; report actual sample size and limitations.

Events contain only the event name, timestamp, and generated report ID, never raw CSV fields or secrets. Onboarding and report views are emitted by actual dashboard interactions, not inferred from report creation. Accepted analysis submissions and validation successes are recorded by the API, and human decisions by the persistence layer. Sample analyses are included in these exploratory logs; they are not real customer evidence. Session identity, repeat-user attribution, PostHog forwarding, and a production North Star metric are not implemented.

## Development checks
Install the development dependencies first. The same gates run in GitHub Actions on Python 3.11 and 3.12:

```bash
python -m pip check
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest -q
```

Run only the Streamlit UI tests:

```bash
python -m pytest -q -m ui --strict-markers
```

These headless AppTest cases exercise both sample datasets, navigation, and approve/reject decisions against an in-process FastAPI client. No running servers, real bills, network calls, or provider credentials are needed. The complete pytest command includes UI tests. Additional tests cover CSV validation, deterministic calculations, source/date restrictions, unsupported factors, privacy, invalid AI responses, persistence, dependency separation, and repository hygiene.

GitHub Actions also runs the UI cases in an explicit step so they cannot be silently omitted from the matrix. The tracked-generated-file test runs when `.git` metadata exists; source archives without Git metadata skip only that check. Workflow/action and Streamlit testing references were checked against official documentation on 2026-10-27; see [CONTRIBUTING.md](CONTRIBUTING.md).

Ruff's formatter enforces LF in Python; [.gitattributes](.gitattributes) applies LF to all maintained text in Git. Databases, caches, virtual environments, build output, and editable-install metadata are ignored and excluded from container build contexts. Runtime and quality commands can recreate local ignored artifacts; those files must never be committed. Stop services before deleting local databases and preserve any reports you need.

## Release preparation

The package and API version are `0.1.0`. [CHANGELOG.md](CHANGELOG.md) records the release candidate, not an already published release. This workspace is a source snapshot without Git metadata; per the Phase 0 decision, no repository, commit, tag, or push is created here. An authorized maintainer must use the actual checkout, obtain green GitHub CI, finalize the changelog date, and then create the annotated `v0.1.0` tag as described in [CONTRIBUTING.md](CONTRIBUTING.md).

## Secondary research
- [FinOps Foundation — State of FinOps](https://data.finops.org/)
- [Cloud Carbon Footprint — Methodology](https://www.cloudcarbonfootprint.org/docs/methodology/)
- [AWS Sustainability — Methodology](https://docs.aws.amazon.com/sustainability/latest/userguide/methodology.html)
- [Google Cloud Carbon Footprint — Methodology](https://docs.cloud.google.com/carbon-footprint/docs/methodology)

These sources inform discovery and methodology design; they do not validate demand for CarbonLens by themselves.

## Delivery target
**MVP target: 8 November 2026.**

Suggested milestones: secondary research → PRD and data contract → upload/validation/calculation → AI explanations and approvals → deployment, beta feedback, and portfolio case study.

## Disclaimer
CarbonLens is an experimental decision-support prototype. Outputs are estimates based on available data, selected methodology, and documented assumptions. It is not a substitute for provider-specific reporting, a verified greenhouse-gas inventory, professional advice, or regulatory compliance assessment.
