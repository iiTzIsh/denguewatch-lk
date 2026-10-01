// Typed client for the FastAPI service (src/api/main.py). Shapes mirror the Pydantic models there.
import { useQuery } from "@tanstack/react-query";
import type { FeatureCollection, Geometry } from "geojson";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, String(detail));
  }
  return res.json() as Promise<T>;
}

export interface Health { status: string; dengue_data_until: string | null; weather_data_until: string | null }
export interface Hotspot {
  rank: number; district: string; province: string; cases: number; cases_per_100k: number | null;
  change_vs_prev_week: number | null; rain_2wk_earlier_mm: number | null;
}
export interface HotspotsResponse { week: string; week_start: string; total_cases: number; districts: Hotspot[]; disclaimer: string }
export interface NationalPoint { week: string; week_start: string; cases: number }
export interface TrendPoint { week: string; week_start: string; cases: number; rain_mm: number | null }
export interface RainPoint { week_start: string; rain_mm: number | null }
export interface ForecastRegion {
  rdhs: string; district: string; cases_now: number;
  pred_cases_2w: number; outbreak_level_2w: number | null; risk_2w: Risk;
  pred_cases_4w: number; outbreak_level_4w: number | null; risk_4w: Risk;
}
export type Risk = "high" | "watch" | "normal" | "unknown";
export interface ForecastResponse { model_version: string; based_on_week_ending: string; regions: ForecastRegion[] }
export interface MOHHotspot { rank: number; moh_area: string; district: string; cases: number; change_vs_prev_week: number; split_from: string | null }
export interface MOHResponse { week: string; listed: number; moh_areas: MOHHotspot[]; note: string }
export interface ModelPerformance {
  model_name: string; horizon_weeks: number; forecasts: number; first_target_week: string; last_target_week: string;
  mae: number; naive_mae: number; skill_vs_naive: number | null; outbreak_weeks: number; alerts: number; correct_alerts: number;
}
export interface DriftStatus {
  base_week_end: string; drift_detected: boolean; n_drifted: number; n_features: number; drift_share: number;
  drifted_features: string[]; checked_at: string;
}
export interface ModelHealth { performance: ModelPerformance[]; drift: DriftStatus | null }
export interface AccuracyPoint { target_week_end: string; actual: number; forecast: number; naive: number; regions: number }
export type DistrictGeo = FeatureCollection<Geometry, { district: string; district_name: string }>;

const long = { staleTime: 5 * 60_000 };
// a missing table is a normal "not built yet" state, not something to retry
const noRetry404 = (n: number, e: Error) => !(e instanceof ApiError && e.status === 404) && n < 2;

export const useHealth = () => useQuery({ queryKey: ["health"], queryFn: () => get<Health>("/health"), ...long });
export const useWeeks = () => useQuery({ queryKey: ["weeks"], queryFn: () => get<string[]>("/weeks"), ...long });
export const useHotspots = (week?: string) =>
  useQuery({ queryKey: ["hotspots", week], queryFn: () => get<HotspotsResponse>(`/hotspots?top=25&week=${week}`), enabled: !!week, ...long });
export const useNational = () => useQuery({ queryKey: ["national"], queryFn: () => get<NationalPoint[]>("/national/trend"), ...long });
export const useForecast = () =>
  useQuery({ queryKey: ["forecast"], queryFn: () => get<ForecastResponse>("/forecast"), retry: noRetry404, ...long });
export const useMOH = (week?: string) =>
  useQuery({ queryKey: ["moh", week], queryFn: () => get<MOHResponse>(`/moh/hotspots?top=200&week=${week}`), enabled: !!week, retry: noRetry404, ...long });
export const useDistrictTrend = (d?: string) =>
  useQuery({ queryKey: ["trend", d], queryFn: () => get<TrendPoint[]>(`/districts/${d}/trend`), enabled: !!d, ...long });
export const useDistrictRain = (d?: string, since?: string) =>
  useQuery({ queryKey: ["rain", d, since], queryFn: () => get<RainPoint[]>(`/districts/${d}/rain?since=${since}`), enabled: !!d && !!since, ...long });
export const useModelHealth = () => useQuery({ queryKey: ["model"], queryFn: () => get<ModelHealth>("/model/health"), ...long });
export const useAccuracy = (h: number) =>
  useQuery({ queryKey: ["accuracy", h], queryFn: () => get<AccuracyPoint[]>(`/model/forecast-vs-actual?horizon=${h}`), ...long });
export const useGeo = () => useQuery({ queryKey: ["geo"], queryFn: () => get<DistrictGeo>("/geo/districts"), staleTime: Infinity });
