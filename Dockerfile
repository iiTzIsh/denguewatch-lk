# ---- DengueWatch LK application image ----
# One image for: setup (init), pipeline runs, dashboard, API. Airflow has its own image (infra/airflow).
# All requirement files resolve together without conflicts (checked with `pip check`).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1) dependencies first (cached layer until requirement files change)
COPY requirements.txt requirements-dbt.txt requirements-dashboard.txt requirements-api.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dbt.txt -r requirements-dashboard.txt \
    -r requirements-api.txt -r requirements-ml.txt

# 2) code
COPY src/ src/
COPY sql/ sql/
COPY reference/ reference/
COPY dbt/ dbt/
COPY dashboard/ dashboard/

# data + logs live OUTSIDE the image (volumes in docker-compose.yml)
ENV DW_DATA_DIR=/app/data \
    DW_LOG_DIR=/app/logs \
    MLFLOW_DISABLE_TELEMETRY=true

CMD ["python", "-m", "src.bootstrap"]
