import { useMemo } from "react";
import type { ForecastResponse, HotspotsResponse, ModelHealth, NationalPoint, DistrictGeo } from "../api";
import { addDays, cssVar, day, fmt, fmt1, title, weekRange } from "../format";
import { useTheme } from "../theme";
import { DistrictMap, breaksFor, type MapDatum } from "./DistrictMap";
import { EChart, chartBase } from "./EChart";
import { Segmented, Skeleton } from "./ui";

export type Metric = "cases" | "rate";

export function Hero({
  hot, national, forecast, model, geo, metric, setMetric, selected, onSelect,
}: {
  hot?: HotspotsResponse; national?: NationalPoint[]; forecast?: ForecastResponse; model?: ModelHealth;
  geo?: DistrictGeo; metric: Metric; setMetric: (m: Metric) => void; selected?: string; onSelect: (d: string) => void;
}) {
  const mapData = useMemo(() => {
    const out: Record<string, MapDatum> = {};
    for (const d of hot?.districts ?? []) {
      out[d.district] = {
        value: metric === "cases" ? d.cases : d.cases_per_100k, cases: d.cases, rate: d.cases_per_100k, change: d.change_vs_prev_week,
      };
    }
    return out;
  }, [hot, metric]);
  const breaks = useMemo(
    () => breaksFor(Object.values(mapData).map((d) => d.value ?? NaN), metric === "rate" ? 1 : 0),
    [mapData, metric],
  );

  return (
    <section aria-labelledby="hero-h" className="grid grid-cols-1 gap-8 pt-6 pb-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-14">
      <div className="order-2 lg:order-1">
        <div className="mb-3 flex items-center justify-between gap-3">
          <span className="text-sm text-ink-2">Colour shows</span>
          <Segmented<Metric>
            label="Map metric" value={metric} onChange={setMetric}
            options={[{ value: "cases", label: "Cases" }, { value: "rate", label: "Per 100,000 people" }]}
          />
        </div>
        {geo && hot ? (
          <DistrictMap
            geo={geo} data={mapData} breaks={breaks} selected={selected} onSelect={onSelect}
            metricLabel={metric === "cases" ? `Dengue cases, week of ${day(hot.week_start)}` : `Cases per 100,000 people (Census 2024), week of ${day(hot.week_start)}`}
          />
        ) : <Skeleton h={560} />}
      </div>
      <div className="order-1 lg:order-2 lg:pt-6">
        {hot ? <Story hot={hot} /> : <Skeleton h={180} />}
        <div className="mt-8">
          {national && hot ? <EpidemicCurve national={national} week={hot.week} /> : <Skeleton h={240} />}
        </div>
        <Facts forecast={forecast} model={model} />
      </div>
    </section>
  );
}

function Story({ hot }: { hot: HotspotsResponse }) {
  const ds = hot.districts;
  const changes = ds.map((d) => d.change_vs_prev_week);
  const known = changes.every((c) => c != null);
  const prev = known ? hot.total_cases - changes.reduce<number>((a, c) => a + (c ?? 0), 0) : null;
  const pct = prev ? Math.round(((hot.total_cases - prev) / prev) * 100) : null;
  const top = ds[0];
  const rateTop = [...ds].filter((d) => d.cases_per_100k != null).sort((a, b) => b.cases_per_100k! - a.cases_per_100k!)[0];
  const rising = ds.filter((d) => (d.change_vs_prev_week ?? 0) > 0).length;

  let trend = "";
  if (pct != null) trend = pct === 0 ? ", about the same as the week before" : `, ${Math.abs(pct)}% ${pct < 0 ? "fewer" : "more"} than the week before`;

  return (
    <div>
      <p className="text-ink-2">{weekRange(hot.week_start)}</p>
      <h1 id="hero-h" className="mt-2 text-[2.25rem] leading-[1.08] font-semibold tracking-[-0.02em] sm:text-[2.875rem]">
        <span className="num">{fmt(hot.total_cases)}</span> dengue cases in Sri Lanka{trend}.
      </h1>
      <p className="mt-4 max-w-[62ch] text-lg leading-relaxed text-ink-2">
        {title(top.district)} reported the most (<span className="num text-ink">{fmt(top.cases)}</span>).
        {rateTop && rateTop.district !== top.district && (
          <> {title(rateTop.district)} has the highest rate, <span className="num text-ink">{fmt1(rateTop.cases_per_100k)}</span> cases per 100,000 people.</>
        )}
        {known && <> Cases went up in <span className="num text-ink">{rising}</span> of {ds.length} districts.</>}
      </p>
    </div>
  );
}

function EpidemicCurve({ national, week }: { national: NationalPoint[]; week: string }) {
  const { resolved } = useTheme();
  const option = useMemo(() => {
    // one slot per calendar week, so an unpublished NDCU week shows as a gap, not a line
    const byStart = new Map(national.map((p) => [p.week_start, p]));
    const slots: { start: string; p?: NationalPoint }[] = [];
    for (let s = national[0].week_start; s <= national[national.length - 1].week_start; s = addDays(s, 7)) {
      slots.push({ start: s, p: byStart.get(s) });
    }
    const peak = national.reduce((a, b) => (b.cases > a.cases ? b : a));
    const sel = slots.findIndex((x) => x.p?.week === week);
    const peakIdx = slots.findIndex((x) => x.p?.week === peak.week);
    const base = chartBase(cssVar);
    const ember = cssVar("--ember");
    // an isolated week can't form a line segment, so draw it as a dot
    const lone = slots.map((x, i) => !!x.p && !slots[i - 1]?.p && !slots[i + 1]?.p);
    return {
      grid: { left: 8, right: 16, top: 28, bottom: 4, containLabel: true },
      tooltip: {
        ...base.tooltip,
        formatter: (ps: { dataIndex: number }[]) => {
          const x = slots[ps[0].dataIndex];
          return x.p
            ? `<b>Week of ${day(x.start)}</b><br/>${fmt(x.p.cases)} cases`
            : `<b>Week of ${day(x.start)}</b><br/>No NDCU report`;
        },
      },
      xAxis: {
        type: "category", data: slots.map((x) => day(x.start)), boundaryGap: false,
        axisLabel: { ...base.axisLabel, interval: 3 }, axisLine: base.axisLine, axisTick: { show: false },
      },
      yAxis: { type: "value", axisLabel: { ...base.axisLabel, formatter: (v: number) => fmt(v) }, splitLine: base.splitLine, splitNumber: 3 },
      series: [{
        type: "line", data: slots.map((x) => x.p?.cases ?? null), connectNulls: false,
        lineStyle: { color: ember, width: 2 }, itemStyle: { color: ember },
        showSymbol: true, symbol: "circle", symbolSize: (_v: unknown, p: { dataIndex: number }) => (lone[p.dataIndex] ? 7 : 0),
        emphasis: { scale: false },
        areaStyle: { color: ember, opacity: 0.08 },
        markPoint: {
          symbol: "circle", symbolSize: 10,
          itemStyle: { color: ember, borderColor: cssVar("--surface"), borderWidth: 2 },
          label: { show: true, position: "top", distance: 8, color: cssVar("--ink"), fontSize: 12,
                   fontFamily: "DW Figures, Atkinson Hyperlegible Next, system-ui", formatter: (p: { name: string }) => p.name },
          data: [
            ...(peakIdx >= 0 && peakIdx !== sel ? [{ name: `Peak ${fmt(peak.cases)}`, coord: [peakIdx, peak.cases] }] : []),
            ...(sel >= 0 ? [{ name: "Selected week", coord: [sel, slots[sel].p!.cases], label: { position: sel > slots.length * 0.8 ? "left" : "top" } }] : []),
          ],
        },
      }],
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [national, week, resolved]);
  return (
    <figure className="m-0">
      <figcaption className="mb-1 text-sm text-ink-2">National weekly cases, 2026 (NDCU weekly updates; gaps = weeks with no report)</figcaption>
      <EChart option={option} height={240} label="Line chart of national weekly dengue cases in 2026" />
    </figure>
  );
}

function Facts({ forecast, model }: { forecast?: ForecastResponse; model?: ModelHealth }) {
  const high = forecast?.regions.filter((r) => r.risk_4w === "high").length;
  const watch = forecast?.regions.filter((r) => r.risk_4w === "watch").length;
  const perf = pickPerformance(model, 4);
  const drift = model?.drift;
  const items: { k: string; v: string; note: string; href: string }[] = [
    forecast
      ? { k: "In 4 weeks", v: `${high} high, ${watch} watch`, note: `of ${forecast.regions.length} health regions`, href: "#forecast" }
      : { k: "In 4 weeks", v: "No forecast yet", note: "run the forecast step", href: "#forecast" },
    perf?.skill_vs_naive != null
      ? { k: "Forecast error", v: `${Math.round(Math.abs(perf.skill_vs_naive) * 100)}% ${perf.skill_vs_naive >= 0 ? "lower" : "higher"}`, note: "than “same as this week”", href: "#model" }
      : { k: "Forecast error", v: "Not measured yet", note: "needs weeks that have happened", href: "#model" },
    drift
      ? { k: "Data drift", v: drift.drift_detected ? "Detected" : "None", note: `${drift.n_drifted} of ${drift.n_features} inputs changed`, href: "#model" }
      : { k: "Data drift", v: "Not checked", note: "runs weekly in Airflow", href: "#model" },
  ];
  return (
    <dl className="mt-8 grid grid-cols-1 gap-y-4 sm:grid-cols-3 sm:divide-x sm:divide-line">
      {items.map((i) => (
        <a key={i.k} href={i.href} className="group block rounded-md sm:px-5 sm:first:pl-0">
          <dt className="text-sm text-ink-2">{i.k}</dt>
          <dd className="m-0">
            <span className="font-display text-xl font-semibold group-hover:underline">{i.v}</span>
            <span className="block text-sm text-ink-3">{i.note}</span>
          </dd>
        </a>
      ))}
    </dl>
  );
}

/** the live champion's track record if it has one, otherwise the as-of replay */
export function pickPerformance(model: ModelHealth | undefined, h: number) {
  const rows = model?.performance.filter((p) => p.horizon_weeks === h) ?? [];
  return rows.find((p) => p.model_name !== "asof-replay" && p.forecasts >= 50) ?? rows.find((p) => p.model_name === "asof-replay") ?? rows[0];
}
