import { useMemo, useState } from "react";
import { ApiError, type ForecastRegion, type Risk } from "../api";
import { useForecast } from "../api";
import { date, fmt, title } from "../format";
import { Notice, RiskBadge, Section, Skeleton } from "./ui";

const ORDER: Record<Risk, number> = { high: 3, watch: 2, normal: 1, unknown: 0 };
const ratio = (p: number, l: number | null) => (l ? p / l : 0);

export function ForecastSection() {
  const q = useForecast();
  const [all, setAll] = useState(false);

  const rows = useMemo(() => {
    const r = [...(q.data?.regions ?? [])];
    r.sort((a, b) =>
      Math.max(ORDER[b.risk_2w], ORDER[b.risk_4w]) - Math.max(ORDER[a.risk_2w], ORDER[a.risk_4w]) ||
      Math.max(ratio(b.pred_cases_2w, b.outbreak_level_2w), ratio(b.pred_cases_4w, b.outbreak_level_4w)) -
      Math.max(ratio(a.pred_cases_2w, a.outbreak_level_2w), ratio(a.pred_cases_4w, a.outbreak_level_4w)));
    return r;
  }, [q.data]);
  const shown = all ? rows : rows.slice(0, 8);

  return (
    <Section
      id="forecast" title="The next 4 weeks"
      intro={q.data
        ? <>Forecast for each of the 26 health regions, made from data up to {date(q.data.based_on_week_ending)} by model version {q.data.model_version}. A region is <b className="font-bold text-ink">high risk</b> when the forecast reaches its usual outbreak level for that time of year, and on <b className="font-bold text-ink">watch</b> from 80% of it.</>
        : "Forecast for each of the 26 health regions, 2 and 4 weeks ahead."}
      aside={<Legend />}
    >
      {q.isPending ? <Skeleton h={420} /> : q.error ? (
        <Notice>
          {q.error instanceof ApiError && q.error.status === 404
            ? <>No forecasts yet. They appear after the weekly run, or run <code className="text-ink">python -m src.ml.predict</code>.</>
            : <>The forecast couldn't be loaded: {q.error.message}</>}
        </Notice>
      ) : (
        <>
          <ul className="divide-y divide-line border-y border-line sm:hidden" aria-label="Forecast per health region">
            {shown.map((r) => (
              <li key={r.rdhs} className="py-3">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-bold">{title(r.rdhs)}{r.rdhs !== r.district && <span className="font-normal text-ink-3"> ({title(r.district)})</span>}</span>
                  <span className="text-sm text-ink-2">this week <span className="num text-ink">{fmt(r.cases_now)}</span></span>
                </div>
                <div className="mt-2 grid grid-cols-[4.5rem_1fr] items-center gap-y-2 text-sm text-ink-2">
                  <span>In 2 weeks</span><Bullet pred={r.pred_cases_2w} level={r.outbreak_level_2w} risk={r.risk_2w} max={rowMax(r)} />
                  <span>In 4 weeks</span><Bullet pred={r.pred_cases_4w} level={r.outbreak_level_4w} risk={r.risk_4w} max={rowMax(r)} />
                </div>
              </li>
            ))}
          </ul>
          <div className="relative hidden overflow-x-auto sm:block">
            <table className="w-full min-w-[720px] border-collapse text-left">
              <caption className="sr-only">Forecast cases and risk per health region</caption>
              <thead>
                <tr className="border-b border-line text-sm text-ink-2">
                  <th scope="col" className="py-2 pr-4 font-normal">Health region</th>
                  <th scope="col" className="py-2 pr-6 text-right font-normal">This week</th>
                  <th scope="col" className="py-2 pr-6 font-normal">In 2 weeks</th>
                  <th scope="col" className="py-2 font-normal">In 4 weeks</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => <Row key={r.rdhs} r={r} />)}
              </tbody>
            </table>
          </div>
          {rows.length > 8 && (
            <button onClick={() => setAll(!all)} className="mt-4 rounded-lg border border-line bg-surface px-4 py-2 text-sm hover:border-ink-3">
              {all ? "Show the top 8" : `Show all ${rows.length} regions`}
            </button>
          )}
        </>
      )}
    </Section>
  );
}

const rowMax = (r: ForecastRegion) =>
  Math.max(r.cases_now, r.pred_cases_2w, r.pred_cases_4w, r.outbreak_level_2w ?? 0, r.outbreak_level_4w ?? 0) * 1.08 || 1;

function Row({ r }: { r: ForecastRegion }) {
  const max = rowMax(r);
  return (
    <tr className="border-b border-line align-middle">
      <th scope="row" className="py-3 pr-4 font-normal">
        <span className="font-bold">{title(r.rdhs)}</span>
        {r.rdhs !== r.district && <span className="block text-sm text-ink-3">{title(r.district)} district</span>}
      </th>
      <td className="num py-3 pr-6 text-right">{fmt(r.cases_now)}</td>
      <td className="py-3 pr-6"><Bullet pred={r.pred_cases_2w} level={r.outbreak_level_2w} risk={r.risk_2w} max={max} /></td>
      <td className="py-3"><Bullet pred={r.pred_cases_4w} level={r.outbreak_level_4w} risk={r.risk_4w} max={max} /></td>
    </tr>
  );
}

/** bar = forecast, tick = outbreak level, light band = watch zone (80-100% of the level) */
function Bullet({ pred, level, risk, max }: { pred: number; level: number | null; risk: Risk; max: number }) {
  const pc = (v: number) => `${Math.min(100, (v / max) * 100)}%`;
  return (
    <div className="flex items-center gap-3">
      <div className="relative h-5 w-36 shrink-0 sm:w-52" aria-hidden>
        <div className="absolute inset-y-[7px] left-0 right-0 rounded-full bg-surface-2" />
        {level != null && (
          <div className="absolute inset-y-[4px] rounded-[2px] bg-watch/30" style={{ left: pc(level * 0.8), width: `calc(${pc(level)} - ${pc(level * 0.8)})` }} />
        )}
        <div className="absolute inset-y-[6px] left-0 rounded-r-[4px] bg-lagoon" style={{ width: pc(pred) }} />
        {level != null && <div className="absolute inset-y-0 w-[2px] rounded-full bg-ink" style={{ left: pc(level) }} />}
      </div>
      <div className="min-w-0 text-sm leading-tight">
        <span className="num font-bold">{fmt(pred)}</span>
        <span className="num text-ink-3"> / {level == null ? "–" : fmt(level)}</span>
        <div className="mt-0.5"><RiskBadge risk={risk} /></div>
      </div>
    </div>
  );
}

function Legend() {
  return (
    <ul className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-ink-2" aria-label="How to read the bars">
      <li className="flex items-center gap-2"><span className="h-2 w-6 rounded-r-[3px] bg-lagoon" aria-hidden />Forecast cases</li>
      <li className="flex items-center gap-2"><span className="h-4 w-[2px] bg-ink" aria-hidden />Outbreak level</li>
      <li className="flex items-center gap-2"><span className="h-3 w-5 rounded-[2px] bg-watch/30" aria-hidden />Watch zone</li>
    </ul>
  );
}
