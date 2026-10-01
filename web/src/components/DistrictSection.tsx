import { useMemo } from "react";
import { useDistrictRain, useDistrictTrend, type HotspotsResponse } from "../api";
import { addDays, cssVar, day, fmt, fmt1, title } from "../format";
import { useTheme } from "../theme";
import { EChart, chartBase } from "./EChart";
import { Picker, Section, Skeleton } from "./ui";

const LEAD_WEEKS = 6; // rain matters before cases, so the rain chart starts earlier

export function DistrictSection({ hot, district, onSelect }: { hot?: HotspotsResponse; district?: string; onSelect: (d: string) => void }) {
  const trend = useDistrictTrend(district);
  const first = trend.data?.[0]?.week_start;
  const since = first ? addDays(first, -7 * LEAD_WEEKS) : undefined;
  const rain = useDistrictRain(district, since);
  const { resolved } = useTheme();

  const names = useMemo(
    () => [...(hot?.districts ?? [])].map((d) => d.district).sort().map((d) => ({ value: d, label: title(d) })),
    [hot],
  );

  const charts = useMemo(() => {
    if (!trend.data?.length || !rain.data || !since) return null;
    const last = trend.data[trend.data.length - 1].week_start;
    const slots: string[] = [];
    for (let s = since; s <= last; s = addDays(s, 7)) slots.push(s);
    const cases = new Map(trend.data.map((p) => [p.week_start, p.cases]));
    const rainBy = new Map(rain.data.map((p) => [p.week_start, p.rain_mm]));
    const base = chartBase(cssVar);
    const common = (unit: string, isCases: boolean) => ({
      grid: { left: 8, right: 12, top: 12, bottom: 4, containLabel: true },
      tooltip: {
        ...base.tooltip, axisPointer: { type: "shadow" as const, shadowStyle: { color: cssVar("--line"), opacity: 0.5 } },
        formatter: (ps: { dataIndex: number; value: number | null }[]) => {
          const v = ps[0].value;
          return `<b>Week of ${day(slots[ps[0].dataIndex])}</b><br/>${v == null ? (isCases ? "No report" : "No data") : `${isCases ? fmt(v) : fmt1(v)} ${unit}`}`;
        },
      },
      xAxis: { type: "category", data: slots.map(day), axisLabel: { ...base.axisLabel, interval: 3 }, axisLine: base.axisLine, axisTick: { show: false } },
      yAxis: { type: "value", splitNumber: 3, axisLabel: { ...base.axisLabel, formatter: (v: number) => fmt(v) }, splitLine: base.splitLine },
    });
    const bar = (color: string) => ({ color, borderRadius: [3, 3, 0, 0] });
    const caseVals = slots.map((s) => cases.get(s) ?? null);
    const rainVals = slots.map((s) => rainBy.get(s) ?? null);

    // a data-derived reading, not a claim of cause
    const peakI = caseVals.reduce<number>((bi, v, i) => ((v ?? -1) > (caseVals[bi] ?? -1) ? i : bi), 0);
    const rainI = rainVals.slice(0, peakI + 1).reduce<number>((bi, v, i) => ((v ?? -1) > (rainVals[bi] ?? -1) ? i : bi), 0);
    const note = peakI > rainI && rainVals[rainI] != null
      ? `Heaviest rain before the peak: ${fmt(rainVals[rainI])} mm in the week of ${day(slots[rainI])}. Cases peaked ${peakI - rainI} weeks later, with ${fmt(caseVals[peakI])} in the week of ${day(slots[peakI])}.`
      : null;

    return {
      cases: { ...common("cases", true), series: [{ type: "bar", data: caseVals, itemStyle: bar(cssVar("--ember")), barCategoryGap: "18%" }] },
      rain: { ...common("mm", false), series: [{ type: "bar", data: rainVals, itemStyle: bar(cssVar("--rain")), barCategoryGap: "18%" }] },
      note,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trend.data, rain.data, since, resolved]);

  return (
    <Section
      id="district" title={district ? `${title(district)} up close` : "District up close"}
      intro="Weekly cases next to weekly rainfall, on the same dates. Mosquitoes need standing water and a few weeks to breed, so rain shows up in cases later."
      aside={<Picker label="District" value={district} onChange={onSelect} options={names} className="min-w-44" />}
    >
      {!charts ? <Skeleton h={300} /> : (
        <>
          {charts.note && <p className="mb-5 max-w-[70ch] text-ink-2">{charts.note}</p>}
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
            <figure className="m-0">
              <figcaption className="mb-1 flex items-center gap-2 text-sm text-ink-2">
                <span className="h-2.5 w-2.5 rounded-[2px] bg-ember" aria-hidden />Dengue cases per week
              </figcaption>
              <EChart option={charts.cases} height={260} label={`Bar chart of weekly dengue cases in ${title(district!)}`} />
            </figure>
            <figure className="m-0">
              <figcaption className="mb-1 flex items-center gap-2 text-sm text-ink-2">
                <span className="h-2.5 w-2.5 rounded-[2px] bg-rain" aria-hidden />Rainfall per week (mm), starting {LEAD_WEEKS} weeks earlier
              </figcaption>
              <EChart option={charts.rain} height={260} label={`Bar chart of weekly rainfall in ${title(district!)}`} />
            </figure>
          </div>
        </>
      )}
    </Section>
  );
}
