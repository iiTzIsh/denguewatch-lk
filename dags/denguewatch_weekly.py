"""
DAG: denguewatch_weekly
Every Monday 07:00 (Sri Lanka time): weather -> silver -> SCD2 -> dbt build (gold + tests)
-> dbt docs + Telegram alert.

Each task runs one of our existing modules (same commands you run by hand),
so the pipeline code stays independent of Airflow.
"""
from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

PROJECT = "/opt/airflow/project"   # mounted by docker-compose.airflow.yml
DBT = "/opt/airflow/dbt_venv/bin/dbt"
DBT_ARGS = "--project-dir dbt --profiles-dir dbt"

# Run date for this DAG run. Scheduled runs have a logical_date; manual runs may not -> use run_after.
RUN_DATE = "{{ (dag_run.logical_date or dag_run.run_after).strftime('%Y-%m-%d') }}"

default_args = {
    "owner": "ishara",
    "retries": 2,                              # try again if a task fails ...
    "retry_delay": timedelta(minutes=5),       # ... after 5 minutes
    "execution_timeout": timedelta(minutes=30),
}

with DAG(
    dag_id="denguewatch_weekly",
    description="Weather -> silver -> SCD2 -> dbt gold star schema + tests",
    schedule="0 7 * * 1",                      # cron: minute 0, hour 7, every Monday
    start_date=pendulum.datetime(2026, 9, 1, tz="Asia/Colombo"),
    catchup=False,                             # don't auto-run all the missed past Mondays
    max_active_runs=1,                         # never two runs writing DuckDB at once
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
        # dbt lives in its own virtualenv in the image (see infra/airflow/Dockerfile)
        bash_command=f"cd {PROJECT} && {DBT} build {DBT_ARGS}",
        retries=0,                             # data-test failure = real problem, retrying won't fix it
    )
    dbt_docs = BashOperator(
        task_id="dbt_docs",
        bash_command=f"cd {PROJECT} && {DBT} docs generate {DBT_ARGS}",
    )

    send_alert = BashOperator(
        task_id="send_alert",
        # Telegram token/chat id come from .env (docker-compose env_file). Sends once per week (idempotent).
        bash_command=f"cd {PROJECT} && python -m src.alerts.telegram",
    )

    # dependencies: left runs before right; docs and alert both wait for a GREEN dbt build
    extract_weather >> load_silver >> scd2_regions >> dbt_build >> [dbt_docs, send_alert]
