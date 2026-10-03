# Airflow image with the pipeline packages; dbt and the ML stack each get their own virtualenv.
FROM apache/airflow:3.3.2

COPY requirements.txt requirements-dbt.txt requirements-ml.txt /tmp/
# Pin apache-airflow so pip cannot change the image's version
RUN pip install --no-cache-dir "apache-airflow==3.3.2" -r /tmp/requirements.txt

# dbt-core pins library versions that clash with Airflow's
RUN python -m venv /opt/airflow/dbt_venv \
 && /opt/airflow/dbt_venv/bin/pip install --no-cache-dir -r /tmp/requirements-dbt.txt

# MLflow/LightGBM pin libraries (SQLAlchemy, Flask) that Airflow pins differently
RUN python -m venv /opt/airflow/ml_venv \
 && /opt/airflow/ml_venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt -r /tmp/requirements-ml.txt
