ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim AS base

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

FROM base AS checks
RUN pip install --no-cache-dir -r requirements-dev.txt
RUN python -m pip check
RUN python -m ruff check .
RUN python -m ruff format --check .
RUN python -m mypy
RUN python -m pytest -q -m "not ui" --strict-markers
RUN python -m pytest -q -m ui --strict-markers

FROM base AS runtime
RUN useradd --create-home carbonlens && mkdir -p /app/.local && chown -R carbonlens:carbonlens /app
USER carbonlens
EXPOSE 8001 8501
CMD ["python", "-m", "uvicorn", "carbonlens.api:app", "--host", "0.0.0.0", "--port", "8001"]