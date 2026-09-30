"""Champion/challenger rules + the full train -> register -> promote flow on a throwaway MLflow store."""
from __future__ import annotations

import pytest

mlflow = pytest.importorskip("mlflow")

from src.ml import train  # noqa: E402
from src.ml.features import serving_frame  # noqa: E402
from tests.test_ml_backtest import full_features  # noqa: E402

GOOD = {"skill_vs_naive_h2": 0.03, "skill_vs_naive_h4": 0.12, "mae_h2": 15.0, "mae_h4": 19.0}


@pytest.mark.parametrize(
    ("new", "champion", "expected"),
    [
        (GOOD, None, True),                                                        # first model
        ({**GOOD, "skill_vs_naive_h2": -0.01}, None, False),                       # loses to naive
        ({**GOOD, "skill_vs_naive_h4": 0.0}, None, False),                         # ties naive = not good enough
        (GOOD, GOOD, True),                                                        # same as champion
        ({**GOOD, "mae_h4": 19.0 * 1.009}, GOOD, True),                            # inside 1% tolerance
        ({**GOOD, "mae_h4": 19.0 * 1.02}, GOOD, False),                            # 2% worse at h=4
    ],
)
def test_decide(new, champion, expected):
    promote, reason = train.decide(new, champion)
    assert promote is expected
    assert reason


def test_train_registers_and_promotes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                                          # local artifacts land here
    monkeypatch.setattr(train, "MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    monkeypatch.setattr(train, "MLFLOW_EXPERIMENT", "test")
    monkeypatch.setattr(train, "MIN_LABELLED_ROWS", 0)
    df = full_features()
    monkeypatch.setattr(train, "load_features", lambda: df)
    # synthetic data: force the gate open so we test the registry mechanics, not the model quality
    monkeypatch.setattr(train, "evaluate", lambda d: dict(GOOD))

    assert train.main() == 0
    assert train.main() == 0                                             # retrain -> v2 replaces v1

    client = mlflow.MlflowClient()
    assert str(client.get_model_version_by_alias(train.MODEL_NAME, train.CHAMPION).version) == "2"
    assert str(client.get_model_version_by_alias(train.MODEL_NAME, train.PREVIOUS).version) == "1"

    model = mlflow.pyfunc.load_model(f"models:/{train.MODEL_NAME}@{train.CHAMPION}")
    pred = model.predict(serving_frame(df.tail(3)))
    assert list(pred.columns) == ["rdhs", "week_start", "week_end", "pred_cases_h2", "pred_cases_h4"]
    assert (pred[["pred_cases_h2", "pred_cases_h4"]] >= 0).all().all()


def test_train_refuses_tiny_data(monkeypatch, tmp_path):
    monkeypatch.setattr(train, "MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    monkeypatch.setattr(train, "load_features", lambda: full_features().head(10))
    assert train.main() == 2
