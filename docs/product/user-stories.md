# User Stories and Acceptance Criteria

## Upload data
As a startup engineering lead, I want to upload a supported cloud-usage CSV so I can analyze the usage represented in it.
- Valid CSV: validate schema and summarize accepted rows.
- Missing columns: identify missing columns.
- Unsupported units/regions: flag affected rows rather than guessing.

## Understand emissions
As a user, I want to see how estimates were calculated.
- Each estimate includes factor/source reference and unit.
- Insufficient inputs produce no numeric estimate.
- Outputs are labelled estimates.

## Review recommendations
As a user, I want a short prioritized list.
- Recommendations are grounded in computed results and available fields.
- Each explains its rationale and caveats.
- Approve/reject does not execute infrastructure changes.

## Improve workflow
As product owner, I want to measure funnel steps.
- Events are consistently defined.
- Analytics omit raw CSV contents, secrets, and unnecessary identifiers.
