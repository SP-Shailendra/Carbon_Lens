# Product Requirements Document (MVP)

## Objective
Test whether a transparent CSV-based cloud-emissions workflow with AI-assisted explanations and human-approved recommendations helps target users interpret results and choose an action.

## In scope
- Upload one normalized CSV format.
- Validate required columns, types, units, and reporting period.
- Calculate only estimates supported by documented factors.
- Show estimate provenance and limitations.
- Select a top-three list from computed data.
- Generate explanations and candidate actions using an LLM.
- Allow approve/reject feedback without executing changes.
- Track core funnel events.

## Out of scope
Live provider integrations, automatic cloud modifications, offsets, enterprise administration, compliance certification.

## Acceptance criteria
1. Invalid files produce actionable errors.
2. Unsupported service/region/unit combinations are marked not estimated.
3. Every numeric estimate traces to a formula, factor, unit, and source.
4. AI cannot override computed numbers.
5. Recommendations are suggestions only.
6. Approvals do not trigger infrastructure changes.
7. Analytics do not include raw upload contents or secrets.

## Risks
Provider CSV differences, incomplete factors, false precision, prompt injection, and limited user validation time.
