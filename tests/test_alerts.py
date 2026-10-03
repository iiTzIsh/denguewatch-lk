"""Telegram alert: message content, idempotency, and the API call (fake session - nothing is sent)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.alerts import telegram as tg

WEEK = "2026-W37"
DF = pd.DataFrame(
    {
        "district": ["gampaha", "colombo", "kandy", "kalutara", "kegalle", "galle", "nuwara_eliya"],
        "cases": [218, 207, 174, 73, 69, 69, 14],
        "change": [-6, -15, 16, 2, 11, 22, -4],
        "week_start": pd.Timestamp("2026-09-07"),
    }
)


def test_message_has_top5_totals_and_disclaimer():
    msg = tg.build_message(WEEK, DF)
    assert "2026-W37" in msg and "07 Sep - 13 Sep 2026" in msg
    assert "<b>824</b> (+26 vs last week)" in msg  # 218+207+174+73+69+69+14 = 824; changes sum to +26
    assert "1. Gampaha: 218 (-6)" in msg and "5. Kegalle: 69 (+11)" in msg
    assert "Galle" not in msg.split("Top 5")[1].split("Biggest")[0]  # 6th place not listed
    assert "Biggest rise: Galle +22" in msg
    assert "not official health advice" in msg


def test_message_without_previous_week():
    msg = tg.build_message(WEEK, DF.assign(change=None))
    assert "vs last week" not in msg and "(n/a)" in msg and "Biggest rise" not in msg


def test_sent_weeks_are_remembered(tmp_path):
    f = tmp_path / "sent.txt"
    assert not tg.already_sent(WEEK, f)
    tg.mark_sent(WEEK, f)
    assert tg.already_sent(WEEK, f) and not tg.already_sent("2026-W38", f)


class FakeResp:
    def __init__(self, code):
        self.status_code, self.text = code, "{}"


class FakeSession:
    def __init__(self, code):
        self.code, self.calls = code, []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        return FakeResp(self.code)


def test_send_posts_html_message():
    s = FakeSession(200)
    tg.send("hello", "TOKEN", "42", session=s)
    url, payload = s.calls[0]
    assert url == "https://api.telegram.org/botTOKEN/sendMessage"
    assert payload == {"chat_id": "42", "text": "hello", "parse_mode": "HTML"}


def test_send_raises_on_error():
    with pytest.raises(tg.AlertError, match="401"):
        tg.send("hello", "BAD", "42", session=FakeSession(401))


def test_dotenv_loader_does_not_override(tmp_path, monkeypatch):
    from src import config

    env = tmp_path / ".env"
    env.write_text("# comment\nDW_TEST_A=from_file\nDW_TEST_B='quoted'\n", encoding="utf-8")
    monkeypatch.setenv("DW_TEST_A", "from_env")
    monkeypatch.delenv("DW_TEST_B", raising=False)
    config._load_dotenv(env)
    import os

    assert os.environ["DW_TEST_A"] == "from_env"  # real env var wins
    assert os.environ["DW_TEST_B"] == "quoted"
    monkeypatch.delenv("DW_TEST_B")


def test_message_shows_highest_rate_when_population_loaded():
    df = DF.assign(cases_per_100k=[9.0, 8.0, 12.5, 6.0, 8.1, 6.4, 1.9])
    assert "Highest rate: Kandy 12.5 per 100,000 people" in tg.build_message(WEEK, df)
    assert "Highest rate" not in tg.build_message(WEEK, DF)  # no census loaded -> no line
