import { ChevronRight } from "lucide-react";
import type { RuleView } from "../../lib/types";
import { styleOf } from "../../lib/status";
import { Chip, cx } from "../ui/primitives";

function EvidenceValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-ink-4">none</span>;
  if (typeof value === "object") {
    return <pre className="num max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-chip bg-surface p-2 text-[11px] leading-4 text-ink-2">{JSON.stringify(value, null, 2)}</pre>;
  }
  return <span className="num break-words">{String(value)}</span>;
}

export function RuleRow({ rule }: { rule: RuleView }) {
  const s = styleOf(rule.outcome);
  const Icon = s.icon;
  const evidence = Object.entries(rule.evidence ?? {});
  const highlighted = rule.outcome === "FAIL" || (rule.outcome === "WARN" && rule.review_reason);
  return (
    <li className={cx("rounded-card border px-3 py-2", highlighted ? cx(s.row, s.border) : "border-line bg-surface")}>
      <details className="group">
        <summary className="flex cursor-pointer list-none items-start gap-2 [&::-webkit-details-marker]:hidden">
          <Icon className={cx("mt-0.5 size-4 shrink-0", s.text)} aria-label={rule.outcome} />
          <span className="min-w-0 flex-1 text-sm text-ink">{rule.message}</span>
          <span className="flex shrink-0 items-center gap-1">
            <Chip className="hidden sm:inline-flex">{rule.rule_id}</Chip>
            {rule.outcome !== "PASS" && rule.outcome !== "SKIPPED" && (
              <Chip tone={rule.severity === "HARD" ? "FAIL" : rule.review_reason ? "WARN" : "neutral"}>{rule.severity}</Chip>
            )}
            {evidence.length > 0 && <ChevronRight className="size-4 text-ink-4 transition-transform group-open:rotate-90" aria-hidden />}
          </span>
        </summary>
        {evidence.length > 0 && (
          <dl className="mt-2 grid gap-x-4 gap-y-1.5 rounded-chip bg-sunken p-2 text-xs sm:grid-cols-[max-content_1fr]">
            <dt className="text-ink-3 sm:hidden">Rule</dt>
            <dd className="num sm:hidden">{rule.rule_id}</dd>
            {evidence.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-ink-3">{k.replaceAll("_", " ")}</dt>
                <dd className="min-w-0 text-ink-2">
                  <EvidenceValue value={v} />
                </dd>
              </div>
            ))}
          </dl>
        )}
      </details>
    </li>
  );
}

export function RuleList({ rules, empty = "No checks recorded yet." }: { rules: RuleView[]; empty?: string }) {
  if (rules.length === 0) return <p className="text-xs text-ink-3">{empty}</p>;
  return (
    <ul className="space-y-1.5">
      {rules.map((r) => (
        <RuleRow key={`${r.stage}-${r.rule_id}`} rule={r} />
      ))}
    </ul>
  );
}
