import { CircleCheck, CircleX, Inbox, UserCheck } from "lucide-react";
import type { KeyboardEvent, ReactNode } from "react";
import { useNavigate } from "react-router";
import { FLAG_LABELS, formatDateTime, formatINR } from "../../lib/format";
import type { RunSummary } from "../../lib/types";
import type { ReviewAction } from "../run/ReviewActions";
import { Button, Chip, cx, StatusPill } from "../ui/primitives";

type Mode = "all" | "review";

function DecisionCell({ run }: { run: RunSummary }) {
  if (run.status !== "DONE") return <StatusPill status={run.status} />;
  const shown = run.effective_decision ?? run.decision ?? "PENDING";
  return (
    <span className="inline-flex items-center gap-1">
      <StatusPill status={shown} />
      {run.reviewer_action && (
        <span title={`Reviewer override (automated: ${run.decision})`} className="text-ink-3">
          <UserCheck className="size-3.5" aria-label="Reviewer override" />
        </span>
      )}
    </span>
  );
}

function Flags({ flags }: { flags: string[] }) {
  if (flags.length === 0) return <span className="text-ink-4">none</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {flags.map((f) => (
        <Chip key={f} tone={f === "DUPLICATE" ? "FAIL" : "WARN"}>
          {FLAG_LABELS[f] ?? f}
        </Chip>
      ))}
    </span>
  );
}

function PoCell({ run, stacked = false }: { run: RunSummary; stacked?: boolean }) {
  if (!run.matched_po) return <span className="text-ink-4">none</span>;
  return (
    <span className={cx("inline-flex gap-1", stacked ? "flex-col items-start" : "items-center")}>
      <span className="num">{run.matched_po}</span>
      {run.po_match_type === "INFERRED" && <Chip tone="WARN">inferred</Chip>}
    </span>
  );
}

function When({ iso }: { iso: string }) {
  const [date, time] = formatDateTime(iso).split(", ");
  return (
    <>
      <div className="num text-sm text-ink-2">{time}</div>
      <div className="num text-[11px] text-ink-4">{date}</div>
    </>
  );
}

function reason(run: RunSummary): string {
  return (run.verdict ?? "").replace(/^(Needs review|Rejected|Approved): /, "");
}

function ReviewButtons({ run, onReview, stacked = false }: { run: RunSummary; onReview: (run: RunSummary, action: ReviewAction) => void; stacked?: boolean }) {
  return (
    <span className={cx("flex gap-1.5", stacked ? "flex-col items-stretch" : "justify-end")} onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
      <Button variant="danger" icon={CircleX} className="h-7 px-2 text-xs" onClick={() => onReview(run, "REJECT")}>
        Reject
      </Button>
      <Button variant="primary" icon={CircleCheck} className="h-7 px-2 text-xs" onClick={() => onReview(run, "APPROVE")}>
        Approve
      </Button>
    </span>
  );
}

export function RunsTable({
  runs,
  mode = "all",
  onReview,
  empty,
}: {
  runs: RunSummary[];
  mode?: Mode;
  onReview?: (run: RunSummary, action: ReviewAction) => void;
  empty: ReactNode;
}) {
  const navigate = useNavigate();
  const open = (run: RunSummary) => navigate(`/run/${run.id}${mode === "review" ? "?queue=review" : ""}`);
  const onKey = (e: KeyboardEvent, run: RunSummary) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      open(run);
    }
  };

  if (runs.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-12 text-center">
        <Inbox className="size-6 text-ink-4" aria-hidden />
        <div className="text-sm text-ink-3">{empty}</div>
      </div>
    );
  }

  const review = mode === "review";
  return (
    <>
      {/* Desktop and tablet: table */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="bg-sunken">
            <tr className="text-label uppercase text-ink-3">
              {!review && <th className="px-4 py-2.5">Processed</th>}
              <th className={cx("py-2.5", review ? "px-4" : "px-2.5")}>Vendor</th>
              <th className="px-2.5 py-2.5">Invoice no.</th>
              <th className="px-2.5 py-2.5 text-right">Amount</th>
              <th className="px-2.5 py-2.5">PO</th>
              {!review && <th className="px-2.5 py-2.5">Decision</th>}
              <th className="px-2.5 py-2.5">{review ? "Reason" : "Flags"}</th>
              {review && <th className="px-4 py-2.5"><span className="sr-only">Action</span></th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {runs.map((run) => (
              <tr
                key={run.id}
                tabIndex={0}
                onClick={() => open(run)}
                onKeyDown={(e) => onKey(e, run)}
                className="cursor-pointer align-top transition-colors hover:bg-sunken focus-visible:bg-accent-50 focus-visible:outline-none"
              >
                {!review && (
                  <td className="whitespace-nowrap px-4 py-3">
                    <When iso={run.created_at} />
                  </td>
                )}
                <td className={cx("max-w-[200px] py-3", review ? "px-4" : "px-2.5")}>
                  <div className="truncate font-medium text-ink">{run.vendor_name ?? "Unknown vendor"}</div>
                  <div className="num truncate text-xs text-ink-4">{run.filename}</div>
                </td>
                <td className="num whitespace-nowrap px-2.5 py-3 text-ink">{run.invoice_number ?? <span className="text-ink-4">missing</span>}</td>
                <td className="num whitespace-nowrap px-2.5 py-3 text-right font-medium text-ink">{run.total ? formatINR(run.total) : ""}</td>
                <td className="whitespace-nowrap px-2.5 py-3">
                  <PoCell run={run} stacked />
                </td>
                {!review && (
                  <td className="whitespace-nowrap px-2.5 py-3">
                    <DecisionCell run={run} />
                  </td>
                )}
                <td className={cx("px-2.5 py-3", review && "min-w-[220px]")}>
                  {review ? (
                    <div className="space-y-1">
                      <div className="text-xs text-ink-2">{reason(run)}</div>
                      <Flags flags={run.flags} />
                    </div>
                  ) : (
                    <Flags flags={run.flags} />
                  )}
                </td>
                {review && onReview && (
                  <td className="whitespace-nowrap px-4 py-3">
                    <ReviewButtons run={run} onReview={onReview} stacked />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Phone: cards */}
      <ul className="divide-y divide-line md:hidden">
        {runs.map((run) => (
          <li key={run.id} tabIndex={0} onClick={() => open(run)} onKeyDown={(e) => onKey(e, run)} className="cursor-pointer space-y-2 px-4 py-3 hover:bg-sunken">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate font-medium text-ink">{run.vendor_name ?? "Unknown vendor"}</div>
                <div className="num truncate text-xs text-ink-3">
                  {run.invoice_number ?? "no invoice no."} · {formatDateTime(run.created_at)}
                </div>
              </div>
              <DecisionCell run={run} />
            </div>
            <div className="flex items-center justify-between gap-2">
              <PoCell run={run} />
              <span className="num font-semibold text-ink">{run.total ? formatINR(run.total) : ""}</span>
            </div>
            {review && <div className="text-xs text-ink-2">{reason(run)}</div>}
            <Flags flags={run.flags} />
            {review && onReview && <ReviewButtons run={run} onReview={onReview} />}
          </li>
        ))}
      </ul>
    </>
  );
}
