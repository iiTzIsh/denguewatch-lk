const nf = new Intl.NumberFormat("en-GB");
const nf1 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

export const fmt = (n: number | null | undefined) => (n == null ? "–" : nf.format(Math.round(n)));
export const fmt1 = (n: number | null | undefined) => (n == null ? "–" : nf1.format(n));
export const signed = (n: number | null | undefined) => (n == null ? "–" : `${n > 0 ? "+" : n < 0 ? "−" : "±"}${nf.format(Math.abs(n))}`);

/** "nuwara_eliya" -> "Nuwara Eliya" */
export const title = (s: string) =>
  s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

// Dates are calendar days, so all maths happens in UTC (no timezone can shift a week by a day).
const parse = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00Z`);
const show = (iso: string, o: Intl.DateTimeFormatOptions) => parse(iso).toLocaleDateString("en-GB", { ...o, timeZone: "UTC" });
export const day = (iso: string) => show(iso, { day: "numeric", month: "short" });
export const date = (iso: string) => show(iso, { day: "numeric", month: "short", year: "numeric" });
export const addDays = (iso: string, n: number) => {
  const d = parse(iso);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};
/** "7–13 September 2026" */
export const weekRange = (startIso: string) => {
  const endIso = addDays(startIso, 6);
  const sameMonth = startIso.slice(5, 7) === endIso.slice(5, 7);
  const left = show(startIso, sameMonth ? { day: "numeric" } : { day: "numeric", month: "long" });
  return `${left}–${show(endIso, { day: "numeric", month: "long", year: "numeric" })}`;
};

/** read a CSS custom property (charts need real colours, not var()) */
export const cssVar = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
