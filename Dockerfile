# ---- DengueWatch LK pipeline image ----
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1) dependencies first (cached layer until requirement files change)
COPY requirements.txt requirements-dbt.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dbt.txt

# 2) code
COPY src/ src/
COPY sql/ sql/
COPY reference/ reference/
COPY dbt/ dbt/

# data + logs live OUTSIDE the image (volumes in docker-compose.yml)
ENV DW_DATA_DIR=/app/data \
    DW_LOG_DIR=/app/logs

CMD ["python", "-m", "src.pipeline"]
