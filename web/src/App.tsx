import { useEffect, useState } from "react";
import { useForecast, useGeo, useHealth, useHotspots, useModelHealth, useNational, useWeeks } from "./api";
import { DistrictSection } from "./components/DistrictSection";
import { ForecastSection } from "./components/ForecastSection";
import { Hero, type Metric } from "./components/Hero";
import { ModelSection } from "./components/ModelSection";
import { Notice, Picker } from "./components/ui";
import { WhereSection } from "./components/WhereSection";
import { date } from "./format";
import { useTheme } from "./theme";

export default function App() {
  const weeks = useWeeks();
  const [week, setWeek] = useState<string>();
  const [metric, setMetric] = useState<Metric>("cases");
  const [district, setDistrict] = useState<string>();

  useEffect(() => {
    if (!week && weeks.data?.length) setWeek(weeks.data[0]);
  }, [weeks.data, week]);

  const hot = useHotspots(week);
  const national = useNational();
  const forecast = useForecast();
  const model = useModelHealth();
  const geo = useGeo();

  useEffect(() => {
    if (!district && hot.data?.districts.length) setDistrict(hot.data.districts[0].district);
  }, [hot.data, district]);

  const pick = (d: string) => {
    setDistrict(d);
    document.getElementById("district")?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  };

  return (
    <div className="min-h-screen">
      <Header week={week} weeks={weeks.data} onWeek={setWeek} />
      <main className="mx-auto max-w-[1240px] px-4 sm:px-8">
        {weeks.error ? (
          <div className="py-16">
            <Notice>
              <b className="text-ink">The data service isn't reachable.</b> Start it with <code className="text-ink">docker compose up -d</code>,
              or locally with <code className="text-ink">uvicorn src.api.main:app</code>, then reload this page.
            </Notice>
          </div>
        ) : weeks.data && weeks.data.length === 0 ? (
          <div className="py-16"><Notice>No weekly data loaded yet. Run <code className="text-ink">python -m src.pipeline</code>.</Notice></div>
        ) : (
          <>
            <Hero
              hot={hot.data} national={national.data} forecast={forecast.data} model={model.data} geo={geo.data}
              metric={metric} setMetric={setMetric} selected={district} onSelect={pick}
            />
            <ForecastSection />
            <WhereSection hot={hot.data} metric={metric} onSelect={pick} />
            <DistrictSection hot={hot.data} district={district} onSelect={setDistrict} />
            <ModelSection />
          </>
        )}
      </main>
      <Footer />
    </div>
  );
}

function Header({ week, weeks, onWeek }: { week?: string; weeks?: string[]; onWeek: (w: string) => void }) {
  const health = useHealth();
  const { mode, setMode } = useTheme();
  const next = mode === "system" ? "light" : mode === "light" ? "dark" : "system";
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-bg/85 backdrop-blur">
      <div className="mx-auto flex max-w-[1240px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-8">
        <a href="#" className="flex items-center gap-2" aria-label="DengueWatch LK home">
          <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden>
            <path d="M16 3C11 11 7 15.5 7 20a9 9 0 0 0 18 0c0-4.5-4-9-9-17z" fill="var(--ember)" />
            <path d="M12 21a4 4 0 0 0 4 4" stroke="var(--surface)" strokeWidth="2" fill="none" strokeLinecap="round" />
          </svg>
          <span className="font-display text-lg font-semibold tracking-[-0.01em]">DengueWatch LK</span>
        </a>
        <nav aria-label="Sections" className="hidden gap-5 text-sm text-ink-2 md:flex">
          <a href="#forecast" className="hover:text-ink">Forecast</a>
          <a href="#where" className="hover:text-ink">Where</a>
          <a href="#district" className="hover:text-ink">Districts</a>
          <a href="#model" className="hover:text-ink">Model</a>
        </nav>
        <div className="ml-auto flex items-center gap-3">
          {health.data?.dengue_data_until && (
            <span className="hidden text-sm text-ink-3 lg:inline">Cases to {date(health.data.dengue_data_until)}</span>
          )}
          {weeks && week && (
            <Picker label="Week" value={week} onChange={onWeek} options={weeks.map((w) => ({ value: w, label: w.replace("-W", ", week ") }))} />
          )}
          <button
            onClick={() => setMode(next)}
            className="rounded-lg border border-line bg-surface p-2 text-ink-2 hover:text-ink"
            aria-label={`Theme: ${mode}. Switch to ${next}`} title={`Theme: ${mode}`}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
              {mode === "dark"
                ? <path d="M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5z" fill="currentColor" />
                : mode === "light"
                  ? <g fill="currentColor"><circle cx="8" cy="8" r="3" /><path d="M8 0v3M8 13v3M0 8h3M13 8h3M2.3 2.3l2.1 2.1M11.6 11.6l2.1 2.1M2.3 13.7l2.1-2.1M11.6 4.4l2.1-2.1" stroke="currentColor" strokeWidth="1.4" /></g>
                  : <g><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M8 2a6 6 0 0 1 0 12z" fill="currentColor" /></g>}
            </svg>
          </button>
        </div>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="mt-16 border-t border-line">
      <div className="mx-auto grid max-w-[1240px] gap-6 px-4 py-10 text-sm text-ink-2 sm:px-8 md:grid-cols-[2fr_3fr]">
        <div>
          <p className="font-display text-base font-semibold text-ink">© 2026 Ishara Madhusanka</p>
          <p className="mt-2">Portfolio project, not official health advice.</p>
          <p className="mt-2">For official figures see the National Dengue Control Unit.</p>
        </div>
        <ul className="space-y-1">
          <li>Cases: <a className="underline" href="https://www.dengue.health.gov.lk/">National Dengue Control Unit</a> weekly updates; history from the Epidemiology Unit's Weekly Epidemiological Report via <a className="underline" href="https://github.com/thiyangt/denguedatahub">denguedatahub</a>.</li>
          <li>Weather: <a className="underline" href="https://open-meteo.com/">Open-Meteo</a> (CC BY 4.0). Population: Census of Population and Housing 2024.</li>
          <li>District boundaries: <a className="underline" href="https://www.geoboundaries.org/">geoBoundaries</a>, from OpenStreetMap (ODbL).</li>
        </ul>
      </div>
    </footer>
  );
}
