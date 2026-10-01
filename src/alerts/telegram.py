"""
Weekly Telegram alert:
  1. this week's top districts by dengue cases       (gold.mart_ndcu_monitoring, NDCU)
  2. regions FORECAST near/above their outbreak level (ml.forecast_latest, written by src.ml.predict)
Part 2 is simply left out if no forecasts exist yet - the cases alert never depends on the model.

Setup (once): create a bot with @BotFather, then put in .env (never committed):
    TELEGRAM_BOT_TOKEN=123456:ABC...
    TELEGRAM_CHAT_ID=123456789

Run:  python -m src.alerts.telegram --dry-run     (print the message, send nothing)
      python -m src.alerts.telegram               (send, once per week - repeats are skipped)
      python -m src.alerts.telegram --force       (send again even if already sent)
"""
from __future__ import annotations

import argparse
import html
import logging
import os
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import requests

from src.config import ALERTS_DIR, DB_PATH
from src.log_setup import setup_logging
from src.reports.dashboard_data import latest_forecast

logger = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/sendMessage"
SENT_FILE = ALERTS_DIR / "telegram_sent_weeks.txt"
TOP_N = 5
MAX_FORECAST_LINES = 5
MAX_FORECAST_AGE_DAYS = 21     # forecasts based on data older than this vs the cases week are flagged as stale


class AlertError(Exception):
    pass


def latest_week(con: duckdb.DuckDBPyConnection) -> tuple[str, pd.DataFrame]:
    row = con.execute("SELECT max(iso_week_key) FROM gold.mart_ndcu_monitoring").fetchone()
    week = row[0] if row else None
    if week is None:
        raise AlertError("No NDCU weeks in the warehouse - run the pipeline first")
    df = con.execute(
        """SELECT district, cases, cases_change_vs_prev_week AS change, week_start, cases_per_100k
           FROM gold.mart_ndcu_monitoring WHERE iso_week_key = ? ORDER BY cases DESC""",
        [week],
    ).df()
    return week, df


def _signed(v: Any) -> str:
    if v is None or v != v:          # None or NaN (NaN is the only value not equal to itself)
        return "n/a"
    return f"{int(v):+d}"


def forecast_lines(fc: pd.DataFrame, cases_week_start: pd.Timestamp | None = None) -> list[str]:
    """Regions at 'watch' or 'high' in the next 2 or 4 weeks; otherwise the closest one."""
    if fc is None or fc.empty:
        return []
    based_on = pd.Timestamp(fc["base_week_end"].iloc[0])
    lines = ["", f"<b>Forecast</b> (model v{html.escape(str(fc['model_version'].iloc[0]))}, "
                 f"case data to {based_on:%d %b})"]
    if cases_week_start is not None and (cases_week_start - based_on).days > MAX_FORECAST_AGE_DAYS:
        return lines + [f"⚠️ Forecast is stale (data only to {based_on:%d %b %Y}) - not shown. Re-run the pipeline."]
    flagged = fc[fc["risk_2w"].isin(["high", "watch"]) | fc["risk_4w"].isin(["high", "watch"])]
    for r in flagged.head(MAX_FORECAST_LINES).to_dict("records"):
        h = 2 if r["risk_2w"] in ("high", "watch") else 4
        level = "HIGH" if r[f"risk_{h}w"] == "high" else "watch"
        lines.append(f"⚠️ {html.escape(str(r['rdhs']).replace('_', ' ').title())}: ~{r[f'pred_{h}w']:,.0f} cases "
                     f"in {h} wks (outbreak level {r[f'level_{h}w']:,.0f}) - {level}")
    if flagged.empty:
        lines.append("No region is forecast near its outbreak level in the next 4 weeks.")
        with_level = fc[fc["level_4w"].notna()]
        if not with_level.empty:
            top = with_level.assign(ratio=with_level["pred_4w"] / with_level["level_4w"]).nlargest(1, "ratio").iloc[0]
            lines.append(f"Closest: {html.escape(str(top['rdhs']).replace('_', ' ').title())} "
                         f"~{top['pred_4w']:,.0f} vs level {top['level_4w']:,.0f} ({top['ratio']:.0%}) in 4 wks")
    return lines


def build_message(week: str, df: pd.DataFrame, top_n: int = TOP_N, forecast: pd.DataFrame | None = None) -> str:
    """Plain, phone-friendly HTML message. Honest wording: highest CASES (not a forecast yet)."""
    start = pd.Timestamp(df["week_start"].iloc[0])
    end = start + pd.Timedelta(days=6)
    total = int(df["cases"].sum())
    has_change = df["change"].notna().any()
    total_change = int(df["change"].sum()) if has_change else None

    lines = [
        f"🦟 <b>DengueWatch LK - {week}</b>",
        f"{start:%d %b} - {end:%d %b %Y}",
        "",
        f"Cases this week (all districts): <b>{total:,}</b>"
        + (f" ({_signed(total_change)} vs last week)" if total_change is not None else ""),
        "",
        f"<b>Top {top_n} districts by cases</b>",
    ]
    def pretty(district: Any) -> str:
        return html.escape(str(district).replace("_", " ").title())

    rows = [{str(k): v for k, v in rec.items()} for rec in df.to_dict("records")]
    for i, row in enumerate(rows[:top_n], 1):
        lines.append(f"{i}. {pretty(row['district'])}: {int(row['cases']):,} ({_signed(row['change'])})")

    with_change = [r for r in rows if _signed(r["change"]) != "n/a"]
    if with_change:
        top_rise = max(with_change, key=lambda r: r["change"])
        if top_rise["change"] > 0:
            lines += ["", f"Biggest rise: {pretty(top_rise['district'])} {_signed(top_rise['change'])}"]

    rated = [r for r in rows if r.get("cases_per_100k") is not None and r["cases_per_100k"] == r["cases_per_100k"]]
    if rated:
        top_rate = max(rated, key=lambda r: r["cases_per_100k"])
        lines.append(f"Highest rate: {pretty(top_rate['district'])} "
                     f"{top_rate['cases_per_100k']:.1f} per 100,000 people")

    lines += forecast_lines(forecast, start) if forecast is not None else []
    has_forecast = forecast is not None and not forecast.empty
    source = "NDCU weekly update" + ("; forecast: DengueWatch model (WER + NDCU cases, Open-Meteo weather)"
                                     if has_forecast else "")
    lines += ["", f"<i>Source: {source}. Portfolio project - not official health advice.</i>"]
    return "\n".join(lines)


def already_sent(week: str, path: Path = SENT_FILE) -> bool:
    return path.exists() and week in path.read_text(encoding="utf-8").split()


def mark_sent(week: str, path: Path = SENT_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(week + "\n")


def send(text: str, token: str, chat_id: str, session: requests.Session | None = None) -> None:
    session = session or requests.Session()
    resp = session.post(API.format(token=token),
                        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=30)
    if resp.status_code != 200:
        # never log the token - the URL contains it
        raise AlertError(f"Telegram returned HTTP {resp.status_code}: {resp.text[:200]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="print the message, don't send")
    parser.add_argument("--force", action="store_true", help="send even if this week was already sent")
    args = parser.parse_args()
    setup_logging()

    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        week, df = latest_week(con)
        fc = latest_forecast(con)
    text = build_message(week, df, forecast=fc)

    if args.dry_run:
        print(text)
        return
    if already_sent(week) and not args.force:
        logger.info("Alert for %s already sent - skipping (use --force to resend)", week)
        return

    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set (add them to .env)")
        raise SystemExit(2)
    try:
        send(text, token, chat_id)
    except (AlertError, requests.RequestException) as exc:
        logger.error("Alert failed: %s", exc)
        raise SystemExit(1) from exc
    mark_sent(week)
    logger.info("Alert sent for %s", week)


if __name__ == "__main__":
    main()
