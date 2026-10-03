// Shared UI pieces: Radix primitives (accessible, keyboard-ready) styled with Tailwind.
import * as Select from "@radix-ui/react-select";
import * as ToggleGroup from "@radix-ui/react-toggle-group";
import type { ReactNode } from "react";
import type { Risk } from "../api";

export function Segmented<T extends string>({
  value, onChange, options, label,
}: { value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; label: string }) {
  return (
    <ToggleGroup.Root
      type="single" value={value} aria-label={label}
      onValueChange={(v) => v && onChange(v as T)}
      className="inline-flex rounded-full border border-line bg-surface-2 p-0.5 text-sm"
    >
      {options.map((o) => (
        <ToggleGroup.Item
          key={o.value} value={o.value}
          className="rounded-full px-3 py-1 text-ink-2 transition-colors hover:text-ink data-[state=on]:bg-surface data-[state=on]:text-ink data-[state=on]:shadow-[0_1px_3px_rgba(15,42,46,.15)]"
        >
          {o.label}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}

export function Picker({
  value, onChange, options, label, className = "",
}: { value?: string; onChange: (v: string) => void; options: { value: string; label: string }[]; label: string; className?: string }) {
  return (
    <Select.Root value={value ?? ""} onValueChange={onChange}>
      <Select.Trigger
        aria-label={label}
        className={`inline-flex items-center justify-between gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm hover:border-ink-3 ${className}`}
      >
        <Select.Value />
        <Select.Icon className="text-ink-3">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden><path d="M3 4.5 6 7.5 9 4.5" stroke="currentColor" strokeWidth="1.5" fill="none" /></svg>
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content position="popper" sideOffset={6}
          className="z-50 max-h-80 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-lg border border-line bg-surface text-ink shadow-[0_10px_30px_rgba(15,42,46,.18)]">
          <Select.Viewport className="p-1">
            {options.map((o) => (
              <Select.Item key={o.value} value={o.value}
                className="cursor-pointer rounded-md px-3 py-1.5 text-sm outline-none data-[highlighted]:bg-surface-2 data-[state=checked]:font-bold">
                <Select.ItemText>{o.label}</Select.ItemText>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}

const RISK: Record<Risk, { label: string; color: string; icon: ReactNode }> = {
  high: {
    label: "High", color: "var(--high)",
    icon: <path d="M6 1.5 11 10.5H1z" fill="currentColor" />,
  },
  watch: {
    label: "Watch", color: "var(--watch)",
    icon: <circle cx="6" cy="6" r="4.5" fill="none" stroke="currentColor" strokeWidth="2" />,
  },
  normal: {
    label: "Normal", color: "var(--normal)",
    icon: <circle cx="6" cy="6" r="2.5" fill="currentColor" />,
  },
  unknown: {
    label: "Not enough history", color: "var(--ink-3)",
    icon: <path d="M2 6h8" stroke="currentColor" strokeWidth="2" />,
  },
};

/** status = colour + icon + word, never colour alone */
export function RiskBadge({ risk }: { risk: Risk }) {
  const r = RISK[risk] ?? RISK.unknown;
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-sm">
      <svg width="12" height="12" viewBox="0 0 12 12" style={{ color: r.color }} aria-hidden>{r.icon}</svg>
      {r.label}
    </span>
  );
}

export function Section({ id, title, intro, aside, children }: {
  id: string; title: string; intro?: ReactNode; aside?: ReactNode; children: ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="border-t border-line pt-10 pb-4">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <h2 id={`${id}-h`} className="text-[1.75rem] leading-tight font-semibold tracking-[-0.01em]">{title}</h2>
          {intro && <p className="mt-2 text-ink-2">{intro}</p>}
        </div>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-dashed border-line bg-surface-2 px-4 py-6 text-ink-2">{children}</div>;
}

export function Skeleton({ h }: { h: number }) {
  return <div className="animate-pulse rounded-lg bg-surface-2" style={{ height: h }} aria-hidden />;
}
