"""
DAG: retrain_monthly
1st of every month 09:00: backtest + train a new forecaster, register it in MLflow, and promote it
to @champion ONLY if it beats the naive baseline and is not worse than the current champion
(rules in src/ml/train.py). A rejected model is not a failure: it stays registered, tagged with the reason.

Needs the MLflow server:  docker compose up -d mlflow
"""
from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

PROJECT = "/opt/airflow/project"
ML_PY = "/opt/airflow/ml_venv/bin/python"     # ML libraries live in their own virtualenv (see infra/airflow/Dockerfile)

with DAG(
    dag_id="retrain_monthly",
    description="Walk-forward backtest -> train -> register -> champion/challenger promotion (MLflow)",
    schedule="0 9 1 * *",
    start_date=pendulum.datetime(2026, 10, 1, tz="Asia/Colombo"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "ishara",
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
        "execution_timeout": timedelta(minutes=45),
    },
    tags=["denguewatch", "ml"],
) as dag:
    BashOperator(
        task_id="train_and_promote",
        bash_command=f"cd {PROJECT} && {ML_PY} -m src.ml.train",
    )
