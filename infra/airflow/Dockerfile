# Official Airflow image + our pipeline's Python packages + dbt and ML each in their OWN virtualenv
FROM apache/airflow:3.3.2

COPY requirements.txt requirements-dbt.txt requirements-ml.txt /tmp/
# Pin apache-airflow to the image's version so pip can't accidentally up/downgrade it
RUN pip install --no-cache-dir "apache-airflow==3.3.2" -r /tmp/requirements.txt

# dbt-core pins library versions that can clash with Airflow's -> separate venv (common industry pattern)
RUN python -m venv /opt/airflow/dbt_venv \
 && /opt/airflow/dbt_venv/bin/pip install --no-cache-dir -r /tmp/requirements-dbt.txt

# MLflow/LightGBM also pin libraries (SQLAlchemy, Flask...) that Airflow pins differently -> own venv too
RUN python -m venv /opt/airflow/ml_venv \
 && /opt/airflow/ml_venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt -r /tmp/requirements-ml.txt
