import { useMemo, useState } from "react";
import { useAccuracy, useModelHealth } from "../api";
import { cssVar, date, day, fmt, title } from "../format";
import { useTheme } from "../theme";
import { EChart, chartBase } from "./EChart";
import { pickPerformance } from "./Hero";
import { Notice, Section, Segmented, Skeleton } from "./ui";

export function ModelSection() {
  const [h, setH] = useState<"2" | "4">("4");
  const model = useModelHealth();
  const acc = useAccuracy(Number(h));
  const perf = pickPerformance(model.data, Number(h));
  const { resolved } = useTheme();

  const option = useMemo(() => {
    if (!acc.data?.length) return null;
    const base = chartBase(cssVar);
    const lagoon = cssVar("--lagoon"), ember = cssVar("--ember"), naive = cssVar("--naive");
    const line = (name: string, key: "actual" | "forecast" | "naive", color: string, dashed = false) => ({
      name, type: "line", data: acc.data.map((p) => Math.round(p[key])),
      lineStyle: { color, width: 2, type: dashed ? [5, 4] : "solid" }, itemStyle: { color },
      symbol: "circle", symbolSize: 8, showSymbol: false,
    });
    return {
      grid: { left: 8, right: 16, top: 16, bottom: 4, containLabel: true },
      tooltip: { ...base.tooltip, valueFormatter: (v: number) => fmt(v) },
      xAxis: { type: "category", data: acc.data.map((p) => day(p.target_week_end)), boundaryGap: false,
               axisLabel: { ...base.axisLabel, interval: 1 }, axisLine: base.axisLine, axisTick: { show: false } },
      yAxis: { type: "value", splitNumber: 4, axisLabel: { ...base.axisLabel, formatter: (v: number) => fmt(v) }, splitLine: base.splitLine },
      series: [line("Actual", "actual", ember), line("Model", "forecast", lagoon), line("Naive", "naive", naive, true)],
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [acc.data, resolved]);

  const drift = model.data?.drift;
  return (
    <Section
      id="model" title="Can the forecast be trusted?"
      intro={<>Every forecast is kept and compared with what really happened, next to a naive guess (“cases stay the same as this week”). The model is only useful if it beats that guess.</>}
      aside={<Segmented<"2" | "4"> label="Forecast horizon" value={h} onChange={setH}
        options={[{ value: "2", label: "2 weeks ahead" }, { value: "4", label: "4 weeks ahead" }]} />}
    >
      <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        <figure className="m-0">
          <figcaption className="mb-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-2">
            <span>National cases per week, forecast made {h} weeks earlier.</span>
            <span className="flex items-center gap-1.5"><Swatch c="var(--ember)" />Actual</span>
            <span className="flex items-center gap-1.5"><Swatch c="var(--lagoon)" />Model</span>
            <span className="flex items-center gap-1.5"><Swatch c="var(--naive)" dashed />Naive</span>
          </figcaption>
          {acc.isPending ? <Skeleton h={300} /> : option ? (
            <EChart option={option} height={300} label={`Line chart: actual national cases vs the model and the naive forecast, ${h} weeks ahead`} />
          ) : <Notice>No forecast has reached its target week yet. Check back after a few weekly runs, or run <code className="text-ink">python -m src.ml.replay</code>.</Notice>}
        </figure>

        <div className="space-y-6">
          {perf ? (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-5">
              <Stat k="Model error" v={`${fmt(perf.mae)}`} note="cases per region-week" />
              <Stat k="Naive error" v={`${fmt(perf.naive_mae)}`} note="cases per region-week" />
              <Stat k="Improvement" v={perf.skill_vs_naive == null ? "–" : `${Math.round(perf.skill_vs_naive * 100)}%`} note="less error than naive" />
              <Stat k="Outbreak weeks caught" v={`${fmt(perf.correct_alerts)} of ${fmt(perf.outbreak_weeks)}`}
                note={`${fmt(perf.alerts)} alerts raised`} />
              <p className="col-span-2 text-sm text-ink-3">
                {perf.model_name === "asof-replay"
                  ? `As-of replay: each week's model was trained only on data available that week. ${fmt(perf.forecasts)} forecasts, target weeks ${date(perf.first_target_week)} to ${date(perf.last_target_week)}.`
                  : `Live ${title(perf.model_name)} forecasts, ${fmt(perf.forecasts)} so far.`}
              </p>
            </dl>
          ) : model.isPending ? <Skeleton h={200} /> : <Notice>No forecast results yet.</Notice>}

          <div className="rounded-lg border border-line bg-surface p-4">
            <h3 className="flex items-center gap-2 text-base font-semibold">
              {drift?.drift_detected && (
                <svg width="14" height="14" viewBox="0 0 12 12" aria-hidden style={{ color: "var(--watch)" }}><path d="M6 1.5 11 10.5H1z" fill="currentColor" /></svg>
              )}
              {drift ? (drift.drift_detected ? "Input data has drifted" : "No data drift") : "Drift not checked yet"}
            </h3>
            {drift && (
              <p className="mt-1 text-sm text-ink-2">
                {drift.n_drifted} of {drift.n_features} model inputs look different from the same months in the last 5 years
                (check of {date(drift.base_week_end)}).
                {drift.drift_detected ? " Automatic retraining was triggered; the new model replaces the current one only if it is more accurate." : ""}
              </p>
            )}
          </div>
        </div>
      </div>
    </Section>
  );
}

function Stat({ k, v, note }: { k: string; v: string; note: string }) {
  return (
    <div>
      <dt className="text-sm text-ink-2">{k}</dt>
      <dd className="m-0">
        <span className="num font-display text-2xl font-semibold">{v}</span>
        <span className="block text-sm text-ink-3">{note}</span>
      </dd>
    </div>
  );
}

function Swatch({ c, dashed }: { c: string; dashed?: boolean }) {
  return (
    <svg width="18" height="6" aria-hidden>
      <line x1="0" y1="3" x2="18" y2="3" stroke={c} strokeWidth="2" strokeDasharray={dashed ? "5 4" : undefined} />
    </svg>
  );
}
