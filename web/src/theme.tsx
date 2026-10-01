import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type Mode = "system" | "light" | "dark";
interface ThemeState { mode: Mode; resolved: "light" | "dark"; setMode: (m: Mode) => void }

const Ctx = createContext<ThemeState>({ mode: "system", resolved: "light", setMode: () => {} });

function readSaved(): Mode {
  try {
    const t = localStorage.getItem("dw-theme");
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<Mode>(readSaved);
  const [systemDark, setSystemDark] = useState(() => matchMedia("(prefers-color-scheme: dark)").matches);

  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const on = () => setSystemDark(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  const setMode = (m: Mode) => {
    setModeState(m);
    const el = document.documentElement;
    if (m === "system") delete el.dataset.theme;
    else el.dataset.theme = m;
    try {
      if (m === "system") localStorage.removeItem("dw-theme");
      else localStorage.setItem("dw-theme", m);
    } catch {
      /* storage blocked: theme still applies for this visit */
    }
  };

  const resolved = mode === "system" ? (systemDark ? "dark" : "light") : mode;
  return <Ctx.Provider value={{ mode, resolved, setMode }}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);
