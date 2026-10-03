# DengueWatch LK application image: setup (init), pipeline runs and the API.
# The web dashboard (web/Dockerfile) and Airflow (infra/airflow/) have their own images.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt requirements-dbt.txt requirements-api.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dbt.txt -r requirements-api.txt -r requirements-ml.txt

COPY src/ src/
COPY reference/ reference/
COPY dbt/ dbt/

# data and logs are mounted as volumes (docker-compose.yml)
ENV DW_DATA_DIR=/app/data \
    DW_LOG_DIR=/app/logs \
    MLFLOW_DISABLE_TELEMETRY=true

CMD ["python", "-m", "src.bootstrap"]
