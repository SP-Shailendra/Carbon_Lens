# Product Metrics Plan

## North Star
Percentage of new users who obtain an approved top-three recommendation list within 10 minutes of starting the workflow.

## Funnel events
1. `onboarding_started`
2. `upload_submitted`
3. `upload_validated`
4. `report_viewed`
5. `recommendation_approved` or `recommendation_rejected`

## Supporting measures
Upload validation success rate, time to report, approval/rejection rate, workflow completion, and qualitative usability issues.

## Guardrails
All estimates have documented provenance; unsupported inputs are not silently estimated; approval does not change cloud resources; analytics do not collect raw bills.

## Reporting
Record sample size, dates, event definitions, and missing data. Do not claim statistical significance for small exploratory samples.
