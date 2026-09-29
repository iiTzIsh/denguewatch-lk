# Official Airflow image + our pipeline's Python packages
FROM apache/airflow:3.3.2

COPY requirements.txt /tmp/requirements.txt
# Pin apache-airflow to the image's version so pip can't accidentally up/downgrade it
RUN pip install --no-cache-dir "apache-airflow==3.3.2" -r /tmp/requirements.txt
