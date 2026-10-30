# Contributing

CarbonLens is proprietary. Contributions require authorization from the copyright holders; this document does not grant redistribution rights. See [LICENSE](LICENSE).

## Development

Use Python 3.11 or 3.12 and run commands from the repository root in an activated virtual environment:

```bash
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest -q
```

Apply mechanical formatting with `python -m ruff format .`. Commit text files with LF line endings. Do not commit generated databases, caches, virtual environments, credentials, or real cloud bills. If ignored files were previously tracked, an authorized maintainer must remove them from the Git index; adding ignore patterns alone does not untrack files.

## Guardrails

- Audit existing behavior before editing and keep the normalized CSV backward compatible.
- Calculated values remain deterministic; AI cannot alter numbers or infrastructure.
- Keep provenance for numeric estimates, unsupported-input refusals, and human approval.
- Do not invent factors, power coefficients, PUE, grid intensities, or provider schemas. Verify official sources and document the URL and access date in code comments and methodology docs. Leave unverified values unconfigured.
- Add regression tests and pass linting, formatting, type checking, and pytest before review.

## Tests and CI

`python -m pytest -q -m ui --strict-markers` runs both Streamlit sample/approval interactions using AppTest and an in-process API. No browser, API keys, or running servers are required. The full test command includes those tests too.

GitHub Actions runs lint, formatting, mypy, backend/repository tests, and an explicit UI test step on Python 3.11 and 3.12. Official references, accessed 2026-10-27:

- https://docs.github.com/en/actions/use-cases-and-examples/building-and-testing/building-and-testing-python
- https://github.com/actions/checkout/tree/v6
- https://github.com/actions/setup-python/tree/v6
- https://docs.streamlit.io/develop/concepts/app-testing/get-started
- https://pypi.org/project/pandas-stubs/ (stub versions match the pandas 2.3 release family)

## Release Checklist

1. Use the actual Git checkout, review the complete diff, and confirm no generated or confidential files are tracked.
2. Obtain green Python 3.11 and 3.12 GitHub CI runs on the intended release commit.
3. Confirm project/API version 0.1.0, finalize the changelog date, and obtain release approval.
4. An authorized maintainer may then create `git tag -a v0.1.0 -m "CarbonLens v0.1.0"` on that commit. Pushing the tag is a separate authorized operation.

This phase prepares files only; it does not initialize Git, commit, tag, or push.