// Building blocks from docs/design-system.md. Status colors always come from lib/status.ts.

import type { LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { styleOf, toneOf, STATUS_LABELS } from "../../lib/status";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

// -- Button -------------------------------------------------------------------

type ButtonVariant = "primary" | "danger" | "neutral" | "ghost";

const BUTTON: Record<ButtonVariant, string> = {
  primary: "bg-approve-700 text-white border-approve-700 hover:bg-approve-800 shadow-card",
  danger: "bg-reject-50 text-reject-600 border-reject-300 hover:bg-reject-100",
  neutral: "bg-surface text-ink border-line hover:border-line-strong hover:bg-sunken",
  ghost: "bg-transparent text-accent-700 border-transparent hover:bg-accent-50",
};

export function Button({
  variant = "neutral",
  icon: Icon,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; icon?: LucideIcon }) {
  return (
    <button
      type="button"
      className={cx(
        "inline-flex h-8 items-center justify-center gap-1.5 rounded-control border px-3 text-sm font-semibold",
        "transition-colors focus-visible:shadow-focus focus-visible:outline-none",
        "disabled:cursor-not-allowed disabled:opacity-50",
        BUTTON[variant],
        className,
      )}
      {...rest}
    >
      {Icon && <Icon className="size-4 shrink-0" aria-hidden />}
      {children}
    </button>
  );
}

// -- Status pill and chip --------------------------------------------------------

export function StatusPill({
  status,
  label,
  size = "sm",
  className,
}: {
  status: string;
  label?: string;
  size?: "sm" | "md";
  className?: string;
}) {
  const s = styleOf(status);
  const Icon = s.icon;
  const spinning = toneOf(status) === "running";
  return (
    <span
      className={cx(
        "inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full border font-semibold",
        size === "sm" ? "h-6 px-2 text-xs" : "h-7 px-2.5 text-sm",
        s.pill,
        className,
      )}
    >
      <Icon className={cx("size-3.5", spinning && "animate-spin")} aria-hidden />
      {label ?? STATUS_LABELS[status] ?? status}
    </span>
  );
}

export function Chip({ children, tone = "neutral", className }: { children: ReactNode; tone?: string; className?: string }) {
  const s = styleOf(tone === "neutral" ? "PENDING" : tone);
  return (
    <span className={cx("num inline-flex items-center whitespace-nowrap rounded-chip border px-1.5 py-px text-[11px] font-medium", s.pill, className)}>
      {children}
    </span>
  );
}

// -- Card ---------------------------------------------------------------------------

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cx("rounded-card border border-line bg-surface shadow-card", className)}>{children}</section>;
}

export function CardHeader({
  icon: Icon,
  title,
  subtitle,
  right,
  className,
}: {
  icon?: LucideIcon;
  title: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cx("flex items-center gap-3 border-b border-line px-4 py-3", className)}>
      {Icon && (
        <span className="grid size-7 shrink-0 place-items-center rounded-control bg-sunken text-ink-2">
          <Icon className="size-4" aria-hidden />
        </span>
      )}
      <div className="min-w-0 flex-1">
        <h2 className="truncate text-base font-semibold text-ink">{title}</h2>
        {subtitle && <p className="truncate text-xs text-ink-3">{subtitle}</p>}
      </div>
      {right}
    </header>
  );
}

// -- Labels, KPI tiles, field boxes ------------------------------------------------------

export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("text-label uppercase text-ink-3", className)}>{children}</div>;
}

export function KpiTile({
  label,
  value,
  sub,
  subTone,
  className,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  subTone?: string;
  className?: string;
}) {
  return (
    <div className={cx("min-w-0 rounded-control border border-line bg-surface px-3 py-2", className)}>
      <Label>{label}</Label>
      <div className="num mt-0.5 truncate text-base font-semibold text-ink">
        {value}
        {sub && <span className={cx("ml-1.5 font-sans text-xs font-medium", subTone ? styleOf(subTone).text : "text-ink-3")}>{sub}</span>}
      </div>
    </div>
  );
}

export function FieldBox({ items, className }: { items: Array<{ label: string; value: ReactNode; hint?: ReactNode }>; className?: string }) {
  return (
    <div className={cx("grid gap-3 rounded-card bg-sunken p-3 sm:grid-cols-3", className)}>
      {items.map((it) => (
        <div key={it.label} className="min-w-0">
          <Label>{it.label}</Label>
          <div className="num mt-1 break-words text-sm font-medium text-ink">{it.value}</div>
          {it.hint && <div className="mt-0.5 text-xs text-ink-3">{it.hint}</div>}
        </div>
      ))}
    </div>
  );
}

export function KeyValueRows({ rows, className }: { rows: Array<[string, ReactNode]>; className?: string }) {
  return (
    <dl className={cx("space-y-2", className)}>
      {rows.map(([k, v]) => (
        <div key={k} className="flex items-baseline justify-between gap-4">
          <dt className="shrink-0 text-xs text-ink-3">{k}</dt>
          <dd className="num min-w-0 text-right text-sm text-ink">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

// -- Bars -------------------------------------------------------------------------

export function ConfidenceBar({ value, threshold = 0.7 }: { value: number; threshold?: number }) {
  const low = value < threshold;
  return (
    <div className="flex items-center gap-2">
      <div className="h-1 w-16 overflow-hidden rounded-full bg-line" aria-hidden>
        <div className={cx("h-full rounded-full", low ? "bg-review-600" : "bg-approve-600")} style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className={cx("num text-xs", low ? "font-semibold text-review-700" : "text-ink-3")}>{value.toFixed(2)}</span>
    </div>
  );
}

export function ProgressBar({ value, tone = "running", label }: { value: number; tone?: string; label?: string }) {
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-accent-100"
      role="progressbar"
      aria-label={label}
      aria-valuenow={Math.round(value * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={cx("h-full rounded-full transition-[width] duration-500", styleOf(tone === "running" ? "RUNNING" : tone).dot)} style={{ width: `${Math.round(Math.min(Math.max(value, 0), 1) * 100)}%` }} />
    </div>
  );
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx("num", className)}>{children}</span>;
}
