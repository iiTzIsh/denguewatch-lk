"""NDCU ingest DAG (Mondays 06:30): download new weekly PDFs, then parse and validate them.

Files that fail validation are quarantined; denguewatch_weekly (07:00) loads the parsed output.
"""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

PROJECT = "/opt/airflow/project"

with DAG(
    dag_id="ndcu_ingest_weekly",
    description="NDCU weekly PDFs -> bronze -> parsed (validated)",
    schedule="30 6 * * 1",
    start_date=pendulum.datetime(2026, 9, 1, tz="Asia/Colombo"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "ishara",
        "retries": 3,
        "retry_delay": timedelta(minutes=20),
        "execution_timeout": timedelta(minutes=20),
    },
    tags=["denguewatch", "ndcu"],
) as dag:
    download = BashOperator(task_id="download_pdfs", bash_command=f"cd {PROJECT} && python -m src.extract.ndcu")
    parse = BashOperator(
        task_id="parse_pdfs",
        bash_command=f"cd {PROJECT} && python -m src.transform.ndcu_parse",
        retries=0,  # validation failures are not transient; see data/quarantine/ndcu/
    )
    parse_moh = BashOperator(
        task_id="parse_moh_tables",
        bash_command=f"cd {PROJECT} && python -m src.transform.ndcu_moh_parse",
        retries=0,  # page 2 MOH tables; failures go to data/quarantine/ndcu_moh/
    )
    download >> parse >> parse_moh
