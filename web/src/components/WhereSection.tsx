import { useState } from "react";
import { ApiError, type HotspotsResponse, useMOH } from "../api";
import { day, fmt, fmt1, signed, title } from "../format";
import type { Metric } from "./Hero";
import { Notice, Section, Skeleton } from "./ui";

export function WhereSection({ hot, metric, onSelect }: { hot?: HotspotsResponse; metric: Metric; onSelect: (d: string) => void }) {
  return (
    <Section
      id="where" title="Where the cases are"
      intro={hot ? <>Districts and the smaller MOH (Medical Officer of Health) areas inside them, week of {day(hot.week_start)}.</> : undefined}
    >
      <div className="grid grid-cols-1 gap-10 lg:grid-cols-2 lg:gap-14">
        {hot ? <DistrictRanking hot={hot} metric={metric} onSelect={onSelect} /> : <Skeleton h={480} />}
        <MOHList week={hot?.week} />
      </div>
    </Section>
  );
}

function DistrictRanking({ hot, metric, onSelect }: { hot: HotspotsResponse; metric: Metric; onSelect: (d: string) => void }) {
  const [all, setAll] = useState(false);
  const val = (d: HotspotsResponse["districts"][number]) => (metric === "cases" ? d.cases : d.cases_per_100k ?? 0);
  const rows = [...hot.districts].sort((a, b) => val(b) - val(a));
  const max = Math.max(...rows.map(val), 1);
  const shown = all ? rows : rows.slice(0, 10);
  return (
    <div>
      <h3 className="mb-3 text-lg font-semibold">Districts by {metric === "cases" ? "cases" : "cases per 100,000 people"}</h3>
      <table className="w-full table-fixed border-collapse text-left">
        <colgroup><col className="w-28 sm:w-32" /><col /><col className="w-16" /></colgroup>
        <caption className="sr-only">Districts ranked by {metric === "cases" ? "cases" : "cases per 100,000"}</caption>
        <thead className="sr-only">
          <tr><th>District</th><th>{metric === "cases" ? "Cases" : "Per 100,000"}</th><th>Change vs week before</th></tr>
        </thead>
        <tbody>
          {shown.map((d) => (
            <tr key={d.district} className="group">
              <th scope="row" className="truncate py-1.5 pr-3 font-normal">
                <button onClick={() => onSelect(d.district)} className="text-left hover:underline" title="Show this district's trend">
                  {title(d.district)}
                </button>
              </th>
              <td className="py-1.5 pr-3">
                <div className="flex items-center gap-2">
                  <div className="min-w-0 flex-1" aria-hidden>
                    <div className="h-3 rounded-r-[4px] bg-ember" style={{ width: `${(val(d) / max) * 100}%`, minWidth: 2 }} />
                  </div>
                  <span className="num w-10 shrink-0 text-sm">{metric === "cases" ? fmt(d.cases) : fmt1(d.cases_per_100k)}</span>
                </div>
              </td>
              <td className="num py-1.5 text-right text-sm text-ink-2">
                <Change n={d.change_vs_prev_week} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-ink-3">
        <span>Change = vs the week before.</span>
        {rows.length > 10 && (
          <button onClick={() => setAll(!all)} className="rounded-lg border border-line bg-surface px-3 py-1.5 text-ink hover:border-ink-3">
            {all ? "Show top 10" : `Show all ${rows.length}`}
          </button>
        )}
      </div>
    </div>
  );
}

function Change({ n }: { n: number | null }) {
  if (n == null) return <span>–</span>;
  const up = n > 0;
  return (
    <span className="inline-flex items-center justify-end gap-1">
      {n !== 0 && (
        <svg width="9" height="9" viewBox="0 0 10 10" aria-hidden className={up ? "text-ember" : "text-ink-3"}>
          <path d={up ? "M5 1 9 8H1z" : "M5 9 1 2h8z"} fill="currentColor" />
        </svg>
      )}
      <span className="sr-only">{up ? "up" : n < 0 ? "down" : "no change"}</span>
      {signed(n)}
    </span>
  );
}

function MOHList({ week }: { week?: string }) {
  const q = useMOH(week);
  const [all, setAll] = useState(false);
  if (!week || q.isPending) return <Skeleton h={480} />;
  if (q.error)
    return (
      <div>
        <h3 className="mb-3 text-lg font-semibold">High-risk MOH areas</h3>
        <Notice>
          {q.error instanceof ApiError && q.error.status === 404
            ? "NDCU didn't list MOH areas for this week, or they haven't been loaded yet."
            : `MOH areas couldn't be loaded: ${q.error.message}`}
        </Notice>
      </div>
    );
  const rows = all ? q.data.moh_areas : q.data.moh_areas.slice(0, 12);
  return (
    <div>
      <h3 className="mb-3 text-lg font-semibold">
        High-risk MOH areas <span className="num font-normal text-ink-3">({q.data.listed} listed)</span>
      </h3>
      <div className="relative overflow-x-auto">
        <table className="w-full border-collapse text-left text-sm">
          <caption className="sr-only">High-risk MOH areas listed by NDCU</caption>
          <thead>
            <tr className="border-b border-line text-ink-2">
              <th scope="col" className="py-2 pr-3 font-normal">MOH area</th>
              <th scope="col" className="py-2 pr-3 font-normal">District</th>
              <th scope="col" className="py-2 pr-3 text-right font-normal">Cases</th>
              <th scope="col" className="py-2 text-right font-normal">Change</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.moh_area} className="border-b border-line">
                <th scope="row" className="py-2 pr-3 font-normal">
                  {m.moh_area}
                  {m.split_from && <span className="block text-xs text-ink-3">split from {m.split_from} (unverified)</span>}
                </th>
                <td className="py-2 pr-3 text-ink-2">{title(m.district)}</td>
                <td className="num py-2 pr-3 text-right font-bold">{fmt(m.cases)}</td>
                <td className="num py-2 text-right text-ink-2"><Change n={m.change_vs_prev_week} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-ink-3">
        <span className="max-w-[48ch]">NDCU lists only high-risk areas. An area missing from the list wasn't high-risk that week; it doesn't mean zero cases.</span>
        {q.data.listed > 12 && (
          <button onClick={() => setAll(!all)} className="rounded-lg border border-line bg-surface px-3 py-1.5 text-ink hover:border-ink-3">
            {all ? "Show top 12" : `Show all ${q.data.listed}`}
          </button>
        )}
      </div>
    </div>
  );
}
