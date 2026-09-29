"""
DAG: denguewatch_weekly
Every Monday 07:00 (Sri Lanka time): pull weather -> silver -> SCD2 regions -> gold + data tests.

Each task runs one of our existing modules (same commands you run by hand),
so the pipeline code stays independent of Airflow.
"""
from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

PROJECT = "/opt/airflow/project"   # mounted by docker-compose.airflow.yml

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
    description="Weather -> silver -> SCD2 -> gold star schema + data tests",
    schedule="0 7 * * 1",                      # cron: minute 0, hour 7, every Monday
    start_date=pendulum.datetime(2026, 9, 1, tz="Asia/Colombo"),
    catchup=False,                             # don't auto-run all the missed past Mondays
    max_active_runs=1,                         # never two runs writing DuckDB at once
    default_args=default_args,
    tags=["denguewatch", "weekly"],
) as dag:
    extract_weather = BashOperator(
        task_id="extract_weather",
        bash_command=f"cd {PROJECT} && python -m src.extract.weather --city all --as-of {RUN_DATE} --days-back 35",
    )
    load_silver = BashOperator(
        task_id="load_silver",
        bash_command=f"cd {PROJECT} && python -m src.load.duckdb_load",
    )
    scd2_regions = BashOperator(
        task_id="scd2_regions",
        bash_command=f"cd {PROJECT} && python -m src.transform.scd2",
    )
    build_gold = BashOperator(
        task_id="build_gold",
        bash_command=f"cd {PROJECT} && python -m src.transform.build_gold",
        retries=0,                             # data-test failure = real problem, retrying won't fix it
    )

    # dependencies: left runs before right
    extract_weather >> load_silver >> scd2_regions >> build_gold
