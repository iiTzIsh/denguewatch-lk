# ---- DengueWatch LK pipeline image ----
# Small official Python base image
FROM python:3.12-slim

# Don't write .pyc files; print logs immediately (important in containers)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1) Install dependencies FIRST (this layer is cached until requirements.txt changes -> fast rebuilds)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Then copy the code (changes often)
COPY src/ src/
COPY sql/ sql/
COPY reference/ reference/

# Data + logs live OUTSIDE the image (mounted as volumes by docker-compose)
ENV DW_DATA_DIR=/app/data \
    DW_LOG_DIR=/app/logs

# Default command: run the whole pipeline
CMD ["python", "-m", "src.pipeline"]
