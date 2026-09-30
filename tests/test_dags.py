"""DAG integrity test - standard in industry CI. Skipped automatically if Airflow isn't installed locally."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("airflow.models")
from airflow.models import DagBag  # noqa: E402


def test_dags_load_without_errors():
    bag = DagBag(dag_folder=str(Path(__file__).parents[1] / "dags"))
    assert bag.import_errors == {}
    assert {"denguewatch_weekly", "wer_ingest_weekly", "ndcu_ingest_weekly", "retrain_monthly"} <= set(bag.dag_ids)


def test_weekly_dag_task_order():
    bag = DagBag(dag_folder=str(Path(__file__).parents[1] / "dags"))
    dag = bag.dags["denguewatch_weekly"]  # read from parsed files, no DB needed
    order = [t.task_id for t in dag.topological_sort()]
    assert order[:4] == ["extract_weather", "load_silver", "scd2_regions", "dbt_build"]
    # docs + forecasts only run after a successful dbt build; the alert waits for the forecasts
    assert dag.get_task("predict_forecasts").upstream_task_ids == {"dbt_build"}
    assert dag.get_task("send_alert").upstream_task_ids == {"predict_forecasts"}
    assert dag.get_task("dbt_docs").upstream_task_ids == {"dbt_build"}


def test_retrain_uses_ml_venv_and_runs_monthly():
    bag = DagBag(dag_folder=str(Path(__file__).parents[1] / "dags"))
    dag = bag.dags["retrain_monthly"]
    task = dag.get_task("train_and_promote")
    assert "/opt/airflow/ml_venv/bin/python -m src.ml.train" in task.bash_command
    assert dag.max_active_runs == 1


def test_drift_triggers_retrain():
    bag = DagBag(dag_folder=str(Path(__file__).parents[1] / "dags"))
    dag = bag.dags["denguewatch_weekly"]
    assert dag.get_task("monitor_drift").upstream_task_ids == {"predict_forecasts"}
    assert dag.get_task("drift_detected").upstream_task_ids == {"monitor_drift"}
    trigger = dag.get_task("trigger_retrain")
    assert trigger.upstream_task_ids == {"drift_detected"}
    assert trigger.trigger_dag_id == "retrain_monthly"
