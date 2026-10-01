// Thin React wrapper around Apache ECharts (tree-shaken: only the chart types we use).
import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, MarkLineComponent, MarkPointComponent, TooltipComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import { LegacyGridContainLabel } from "echarts/features";
import type { EChartsCoreOption } from "echarts/core";

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, MarkLineComponent, MarkPointComponent, SVGRenderer, LegacyGridContainLabel]);

export function EChart({ option, height, label }: { option: EChartsCoreOption; height: number; label: string }) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!el.current) return;
    const c = echarts.init(el.current, undefined, { renderer: "svg" });
    chart.current = c;
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(el.current);
    return () => {
      ro.disconnect();
      c.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    chart.current?.setOption({ animation: !reduce, animationDuration: 500, ...option }, true);
  }, [option]);

  return <div ref={el} role="img" aria-label={label} style={{ height, width: "100%" }} />;
}

/** shared axis/tooltip styling read from the current theme's CSS variables */
export function chartBase(c: (v: string) => string) {
  const axisLabel = { color: c("--ink-2"), fontFamily: "DW Figures, Atkinson Hyperlegible Next, system-ui", fontSize: 12 };
  return {
    textStyle: { fontFamily: "DW Figures, Atkinson Hyperlegible Next, system-ui" },
    axisLabel,
    splitLine: { lineStyle: { color: c("--line"), type: [2, 4] as number[] } },
    axisLine: { lineStyle: { color: c("--line") } },
    tooltip: {
      trigger: "axis" as const,
      backgroundColor: c("--surface"),
      borderColor: c("--line"),
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: c("--ink"), fontSize: 13, fontFamily: "DW Figures, Atkinson Hyperlegible Next, system-ui" },
      extraCssText: "box-shadow: 0 6px 24px rgba(15,42,46,.14); border-radius: 8px;",
      axisPointer: { type: "line" as const, lineStyle: { color: c("--ink-3"), width: 1 } },
    },
  };
}
