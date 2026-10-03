"""Weekly pipeline DAG (Mondays 07:00 Asia/Colombo).

Weather -> silver -> SCD2 -> dbt build -> @champion forecasts -> Telegram alert, plus dbt docs.
A drift check after the forecasts triggers retrain_monthly early when drift is detected.
"""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import ShortCircuitOperator
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import DAG

PROJECT = "/opt/airflow/project"  # mounted by docker-compose.airflow.yml
DBT = "/opt/airflow/dbt_venv/bin/dbt"
DBT_ARGS = "--project-dir dbt --profiles-dir dbt"
ML_PY = "/opt/airflow/ml_venv/bin/python"

# Manual runs may have no logical_date; fall back to run_after.
RUN_DATE = "{{ (dag_run.logical_date or dag_run.run_after).strftime('%Y-%m-%d') }}"


def _drift_detected() -> bool:
    """Gate for the retrain trigger; imports lazily so DAG parsing stays light."""
    from src.ml.monitor import latest_drift_detected

    return latest_drift_detected()


default_args = {
    "owner": "ishara",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(minutes=30),
}

with DAG(
    dag_id="denguewatch_weekly",
    description="Weather -> silver -> SCD2 -> dbt gold star schema + tests",
    schedule="0 7 * * 1",
    start_date=pendulum.datetime(2026, 9, 1, tz="Asia/Colombo"),
    catchup=False,
    max_active_runs=1,  # DuckDB allows a single writer
    default_args=default_args,
    tags=["denguewatch", "weekly"],
) as dag:
    extract_weather = BashOperator(
        task_id="extract_weather",
        bash_command=f"cd {PROJECT} && python -m src.extract.weather --district all --as-of {RUN_DATE} --days-back 35",
    )
    load_silver = BashOperator(
        task_id="load_silver",
        bash_command=f"cd {PROJECT} && python -m src.load.duckdb_load",
    )
    scd2_regions = BashOperator(
        task_id="scd2_regions",
        bash_command=f"cd {PROJECT} && python -m src.transform.scd2",
    )
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"cd {PROJECT} && {DBT} build {DBT_ARGS}",
        retries=0,  # data-test failures are not transient
    )
    dbt_docs = BashOperator(
        task_id="dbt_docs",
        bash_command=f"cd {PROJECT} && {DBT} docs generate {DBT_ARGS}",
    )

    predict = BashOperator(
        task_id="predict_forecasts",
        # --soft: without MLflow or a champion, warn and let the cases-only alert go out
        bash_command=f"cd {PROJECT} && {ML_PY} -m src.ml.predict --soft",
    )

    send_alert = BashOperator(
        task_id="send_alert",
        # Credentials come from .env; sends at most once per week.
        bash_command=f"cd {PROJECT} && python -m src.alerts.telegram",
    )

    monitor_drift = BashOperator(
        task_id="monitor_drift",
        bash_command=f"cd {PROJECT} && {ML_PY} -m src.ml.monitor",
    )
    drift_gate = ShortCircuitOperator(
        task_id="drift_detected",
        python_callable=_drift_detected,
        ignore_downstream_trigger_rules=True,
    )
    retrain = TriggerDagRunOperator(
        task_id="trigger_retrain",
        trigger_dag_id="retrain_monthly",
        skip_when_already_exists=True,
    )

    extract_weather >> load_silver >> scd2_regions >> dbt_build >> [dbt_docs, predict]
    predict >> send_alert
    predict >> monitor_drift >> drift_gate >> retrain
