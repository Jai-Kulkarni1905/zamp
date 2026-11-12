import type { LucideIcon } from "lucide-react";
import { cx } from "./primitives";

export interface TabItem<K extends string> {
  key: K;
  label: string;
  icon?: LucideIcon;
  count?: number;
  /** Highlight the count (e.g. items waiting for review). */
  attention?: boolean;
}

/** Underlined tab bar with count badges, like the nav in the reference ("Match Queue 14 pending"). */
export function Tabs<K extends string>({ items, active, onChange }: { items: TabItem<K>[]; active: K; onChange: (key: K) => void }) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto overflow-y-hidden border-b border-line [scrollbar-width:none]">
      {items.map(({ key, label, icon: Icon, count, attention }) => {
        const on = key === active;
        return (
          <button
            key={key}
            role="tab"
            type="button"
            aria-selected={on}
            onClick={() => onChange(key)}
            className={cx(
              "-mb-px inline-flex h-10 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-semibold transition-colors",
              "focus-visible:shadow-focus focus-visible:outline-none",
              on ? "border-accent-600 text-accent-800" : "border-transparent text-ink-3 hover:text-ink",
            )}
          >
            {Icon && <Icon className="size-4" aria-hidden />}
            {label}
            {count !== undefined && (
              <span
                className={cx(
                  "num rounded-full px-1.5 text-[11px] font-semibold leading-5",
                  attention && count > 0 ? "bg-accent-600 text-white" : on ? "bg-accent-100 text-accent-800" : "bg-sunken text-ink-3",
                )}
              >
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
