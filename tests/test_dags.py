"""DAG integrity test - standard in industry CI. Skipped automatically if Airflow isn't installed locally."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("airflow.models")
from airflow.models import DagBag  # noqa: E402


def test_dags_load_without_errors():
    bag = DagBag(dag_folder=str(Path(__file__).parents[1] / "dags"))
    assert bag.import_errors == {}
    assert {"denguewatch_weekly", "wer_ingest_weekly"} <= set(bag.dag_ids)


def test_weekly_dag_task_order():
    bag = DagBag(dag_folder=str(Path(__file__).parents[1] / "dags"))
    dag = bag.dags["denguewatch_weekly"]  # read from parsed files, no DB needed
    assert [t.task_id for t in dag.topological_sort()] == [
        "extract_weather", "load_silver", "scd2_regions", "dbt_build", "dbt_docs"
    ]
