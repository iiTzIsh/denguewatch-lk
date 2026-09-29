"""
DAG: wer_ingest_weekly
Every Monday 06:00: list WER PDF links (bronze). Separate DAG on purpose:
if the government site is down (it often is), weather + gold still run.
"""
from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

PROJECT = "/opt/airflow/project"

with DAG(
    dag_id="wer_ingest_weekly",
    description="Scrape WER listing page -> bronze pdf_links.csv",
    schedule="0 6 * * 1",
    start_date=pendulum.datetime(2026, 9, 1, tz="Asia/Colombo"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "ishara",
        "retries": 3,
        "retry_delay": timedelta(minutes=30),   # flaky source -> wait longer between tries
        "execution_timeout": timedelta(minutes=15),
    },
    tags=["denguewatch", "wer"],
) as dag:
    BashOperator(
        task_id="list_wer_pdfs",
        bash_command=f"cd {PROJECT} && python -m src.extract.wer_links",
    )
