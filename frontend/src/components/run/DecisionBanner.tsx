import { LoaderCircle } from "lucide-react";
import { DECISION_LABELS, FLAG_LABELS, formatINR, formatMs, isNegative, STAGE_LABELS } from "../../lib/format";
import { styleOf } from "../../lib/status";
import type { ExtractedFieldRow, RunDetail, StageView } from "../../lib/types";
import { Chip, cx, KpiTile } from "../ui/primitives";

export function DecisionBanner({ run, stages, live }: { run: RunDetail; stages: StageView[]; live: boolean }) {
  const decision = run.effective_decision ?? run.decision;
  const working = run.status === "QUEUED" || run.status === "RUNNING" || (live && !run.decision && run.status !== "ERROR");
  const errored = run.status === "ERROR";
  const tone = working ? "RUNNING" : errored ? "ERROR" : decision ?? "PENDING";
  const s = styleOf(tone);
  const Icon = working ? LoaderCircle : s.icon;
  // Between two stages nothing is RUNNING for a moment; name the next one instead.
  const current = stages.find((x) => x.status === "RUNNING") ?? stages.find((x) => x.status === "PENDING");
  const finished = stages.filter((x) => !["PENDING", "RUNNING"].includes(x.status)).length;

  const title = working
    ? run.status === "QUEUED" && finished === 0
      ? "Queued: waiting for earlier invoices to finish"
      : `Processing: ${current ? STAGE_LABELS[current.stage] : "finishing"} (${finished}/10)`
    : errored
      ? "Could not finish this run"
      : run.reviewer_action
        ? `${run.reviewer_action === "APPROVE" ? "Approved" : "Rejected"} by a reviewer: "${run.reviewer_note ?? ""}"`
        : run.explanation?.verdict ?? DECISION_LABELS[decision ?? ""] ?? "";

  const counted = run.rules.filter((r) => r.outcome !== "SKIPPED");
  const passed = counted.filter((r) => r.outcome === "PASS").length;
  const fields = (stages.find((x) => x.stage === "extract")?.payload["fields"] as ExtractedFieldRow[] | undefined) ?? [];
  const required = fields.filter((f) => f.required && f.value !== null);
  const missing = fields.filter((f) => f.required && f.value === null).length;
  const minConf = required.length ? Math.min(...required.map((f) => f.confidence)) : null;
  const after = run.po && run.total ? stages.find((x) => x.stage === "amount")?.payload["po"] : null;
  const remainingAfter = after && typeof after === "object" ? (after as { remaining_after: string | null }).remaining_after : null;

  return (
    <section className={cx("rounded-panel border px-4 py-3", working ? "border-accent-200 bg-accent-50" : cx(s.row, s.border))}>
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <span className={cx("grid size-9 shrink-0 place-items-center rounded-control", working ? "bg-accent-100 text-accent-700" : s.solid)}>
            <Icon className={cx("size-5", working && "animate-spin")} aria-hidden />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-base font-semibold text-ink">{title}</h1>
              {!working && run.decision && (
                <span className={cx("rounded-chip px-1.5 py-px text-[11px] font-bold uppercase tracking-wide", s.solid)}>
                  {DECISION_LABELS[decision ?? ""]}
                </span>
              )}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-ink-2">
              {errored && <span className="text-reject-700">{run.error}</span>}
              {run.reviewer_action && (
                <span>
                  Automated: {run.explanation?.verdict ?? DECISION_LABELS[run.decision ?? ""]}
                </span>
              )}
              {run.flags.map((f) => (
                <Chip key={f} tone={f === "DUPLICATE" ? "FAIL" : "WARN"}>
                  {FLAG_LABELS[f] ?? f}
                </Chip>
              ))}
              {!working && !errored && run.flags.length === 0 && !run.reviewer_action && <span>No flags raised.</span>}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:w-[560px] xl:shrink-0">
          <KpiTile label="Invoice total" value={run.total ? formatINR(run.total) : "..."} />
          <KpiTile
            label="PO left after"
            value={remainingAfter ? formatINR(remainingAfter) : run.matched_po ? "..." : "No PO"}
            subTone={remainingAfter && isNegative(remainingAfter) ? "WARN" : undefined}
          />
          <KpiTile label="Checks passed" value={counted.length ? `${passed}/${counted.length}` : "..."} />
          {missing > 0 ? (
            <KpiTile label="Required fields" value={`${missing} missing`} sub="not printed" subTone="WARN" />
          ) : (
            <KpiTile
              label="Min confidence"
              value={minConf !== null ? minConf.toFixed(2) : "..."}
              sub={minConf !== null ? (minConf < 0.7 ? "Low" : "High") : undefined}
              subTone={minConf !== null ? (minConf < 0.7 ? "WARN" : "PASS") : undefined}
            />
          )}
        </div>
      </div>
      {!working && run.duration_ms !== null && (
        <p className="num mt-2 text-right text-[11px] text-ink-4">Processed in {formatMs(run.duration_ms)}</p>
      )}
    </section>
  );
}
