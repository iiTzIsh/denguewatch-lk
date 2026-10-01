// Choropleth of Sri Lanka's 25 districts (MapLibre GL, no basemap: the island itself is the picture).
import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type ExpressionSpecification, type GeoJSONSource } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { DistrictGeo } from "../api";
import { cssVar, fmt, fmt1, signed, title } from "../format";
import { useTheme } from "../theme";

export interface MapDatum { value: number | null; cases: number; rate: number | null; change: number | null }

const ISLAND: [[number, number], [number, number]] = [[79.52, 5.88], [81.92, 9.86]];

/** 4 thresholds -> 5 classes, from quantiles, rounded to readable numbers */
export function breaksFor(values: number[], decimals: number): number[] {
  const v = values.filter((x) => Number.isFinite(x)).sort((a, b) => a - b);
  if (v.length < 5) return [];
  const round = (x: number) => {
    if (decimals > 0) return Number(x.toFixed(decimals));
    const mag = 10 ** Math.max(0, Math.floor(Math.log10(Math.max(x, 1))) - 1);
    return Math.round(x / mag) * mag;
  };
  const out: number[] = [];
  for (const q of [0.2, 0.4, 0.6, 0.8]) {
    const b = round(v[Math.floor(q * (v.length - 1))]);
    if (!out.length || b > out[out.length - 1]) out.push(b);
  }
  return out;
}

export function DistrictMap({
  geo, data, breaks, metricLabel, selected, onSelect,
}: {
  geo: DistrictGeo; data: Record<string, MapDatum>; breaks: number[]; metricLabel: string;
  selected?: string; onSelect: (d: string) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [hover, setHover] = useState<{ d: string; x: number; y: number } | null>(null);
  const { resolved } = useTheme();
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  const fc = useMemo(() => ({
    ...geo,
    features: geo.features.map((f) => ({
      ...f,
      properties: { ...f.properties, v: data[f.properties.district]?.value ?? -1 },
    })),
  }), [geo, data]);

  // create once
  useEffect(() => {
    if (!box.current) return;
    const m = new maplibregl.Map({
      container: box.current,
      style: { version: 8, sources: {}, layers: [] },
      bounds: ISLAND,
      fitBoundsOptions: { padding: 12 },
      interactive: true,
      dragPan: false, scrollZoom: false, boxZoom: false, dragRotate: false,
      keyboard: false, doubleClickZoom: false, touchZoomRotate: false, touchPitch: false,
      attributionControl: false,
    });
    m.on("load", () => {
      m.addSource("d", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addLayer({ id: "fill", type: "fill", source: "d" });
      m.addLayer({ id: "edge", type: "line", source: "d" });
      m.addLayer({ id: "hover", type: "line", source: "d", filter: ["==", ["get", "district"], ""] });
      m.addLayer({ id: "sel", type: "line", source: "d", filter: ["==", ["get", "district"], ""] });
      setReady(true);
    });
    m.on("mousemove", "fill", (e) => {
      const d = e.features?.[0]?.properties?.district as string | undefined;
      m.getCanvas().style.cursor = d ? "pointer" : "";
      if (d) setHover({ d, x: e.point.x, y: e.point.y });
    });
    m.on("mouseleave", "fill", () => {
      m.getCanvas().style.cursor = "";
      setHover(null);
    });
    m.on("click", "fill", (e) => {
      const d = e.features?.[0]?.properties?.district as string | undefined;
      if (d) onSelectRef.current(d);
    });
    const ro = new ResizeObserver(() => {
      m.resize();
      m.fitBounds(ISLAND, { padding: 12, animate: false });
    });
    ro.observe(box.current);
    map.current = m;
    return () => {
      ro.disconnect();
      m.remove();
      map.current = null;
    };
  }, []);

  // data + colours
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    (m.getSource("d") as GeoJSONSource).setData(fc);
    const ramp = [1, 2, 3, 4, 5].map((i) => cssVar(`--ramp-${i}`));
    const steps: (string | number)[] = [ramp[0]];
    breaks.forEach((b, i) => steps.push(b, ramp[i + 1]));
    const color = ["case", ["<", ["get", "v"], 0], cssVar("--ramp-0"),
      ["step", ["get", "v"], ...steps]] as unknown as ExpressionSpecification;
    m.setPaintProperty("fill", "fill-color", color);
    m.setPaintProperty("edge", "line-color", cssVar("--surface"));
    m.setPaintProperty("edge", "line-width", 1.2);
    m.setPaintProperty("hover", "line-color", cssVar("--ink"));
    m.setPaintProperty("hover", "line-width", 1.5);
    m.setPaintProperty("sel", "line-color", cssVar("--ink"));
    m.setPaintProperty("sel", "line-width", 2.5);
  }, [fc, breaks, ready, resolved]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    m.setFilter("hover", ["==", ["get", "district"], hover?.d ?? ""]);
    m.setFilter("sel", ["==", ["get", "district"], selected ?? ""]);
  }, [hover?.d, selected, ready]);

  const h = hover ? data[hover.d] : undefined;
  const ramp = [1, 2, 3, 4, 5];
  const dec = breaks.some((b) => !Number.isInteger(b));
  const f = (n: number) => (dec ? fmt1(n) : fmt(n));

  return (
    <figure className="m-0">
      <div className="relative">
        <div ref={box} className="h-[460px] w-full sm:h-[560px]" aria-label={`Map of Sri Lanka's districts coloured by ${metricLabel}`} role="img" />
        {hover && (
          <div
            className="pointer-events-none absolute z-10 min-w-44 rounded-lg border border-line bg-surface px-3 py-2 text-sm shadow-[0_6px_24px_rgba(15,42,46,.14)]"
            style={{ left: Math.min(hover.x + 14, (box.current?.clientWidth ?? 300) - 190), top: hover.y + 14 }}
          >
            <div className="font-display text-base font-semibold">{title(hover.d)}</div>
            {h ? (
              <dl className="num mt-1 grid grid-cols-[1fr_auto] gap-x-4 text-ink-2">
                <dt>Cases</dt><dd className="text-right text-ink">{fmt(h.cases)}</dd>
                <dt>Per 100,000</dt><dd className="text-right text-ink">{fmt1(h.rate)}</dd>
                <dt>vs week before</dt><dd className="text-right text-ink">{signed(h.change)}</dd>
              </dl>
            ) : <p className="mt-1 text-ink-2">No report this week</p>}
          </div>
        )}
      </div>
      {breaks.length > 0 && (
        <figcaption className="mt-2 text-sm text-ink-2">
          <div className="flex items-end gap-0.5" aria-hidden>
            {ramp.map((i) => (
              <div key={i} className="flex-1">
                <div className="h-2.5 rounded-[2px]" style={{ background: `var(--ramp-${i})` }} />
              </div>
            ))}
          </div>
          <div className="num relative mt-1 h-4 text-xs">
            {breaks.map((b, i) => (
              <span key={b} className="absolute -translate-x-1/2" style={{ left: `${(i + 1) * 20}%` }}>
                {f(b)}
              </span>
            ))}
          </div>
          <p className="mt-1">{metricLabel}. Click a district to see its trend.</p>
        </figcaption>
      )}
    </figure>
  );
}
