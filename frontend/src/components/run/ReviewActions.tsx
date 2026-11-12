import { CircleCheck, CircleX, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";
import { formatINR } from "../../lib/format";
import type { RunDetail, RunSummary } from "../../lib/types";

export type ReviewTarget = Pick<RunSummary, "id" | "total" | "matched_po">;
import { Button, cx } from "../ui/primitives";

export type ReviewAction = "APPROVE" | "REJECT";
type Action = ReviewAction;

/** Approve / Reject for NEEDS_REVIEW runs. A note is required and the override is final (A48). */
export function ReviewActions({ run, onDone }: { run: RunDetail; onDone: (run: RunDetail) => void }) {
  const [action, setAction] = useState<Action | null>(null);
  if (run.status !== "DONE" || run.decision !== "NEEDS_REVIEW" || run.reviewer_action) return null;
  return (
    <>
      <div className="flex items-center gap-2">
        <Button variant="danger" icon={CircleX} onClick={() => setAction("REJECT")}>
          Reject
        </Button>
        <Button variant="primary" icon={CircleCheck} onClick={() => setAction("APPROVE")}>
          Approve
          {run.total && <span className="num ml-1 rounded-chip bg-approve-800/60 px-1.5 py-px text-xs">{formatINR(run.total)}</span>}
        </Button>
      </div>
      {action && <ReviewDialog run={run} action={action} onClose={() => setAction(null)} onDone={onDone} />}
    </>
  );
}

export function ReviewDialog({ run, action, onClose, onDone }: { run: ReviewTarget; action: Action; onClose: () => void; onDone: (run: RunDetail) => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    ref.current?.showModal();
  }, []);

  const approve = action === "APPROVE";
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      onDone(await api.review(run.id, action, note.trim()));
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      className="m-auto w-[min(92vw,480px)] rounded-panel border border-line bg-surface p-0 text-ink shadow-raised backdrop:bg-ink/30"
    >
      <form
        method="dialog"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <header className="flex items-center gap-2 border-b border-line px-4 py-3">
          <h2 className="flex-1 text-base font-semibold">{approve ? "Approve this invoice" : "Reject this invoice"}</h2>
          <button type="button" onClick={onClose} className="grid size-7 place-items-center rounded-control text-ink-3 hover:bg-sunken" aria-label="Close">
            <X className="size-4" />
          </button>
        </header>
        <div className="space-y-3 px-4 py-4">
          <p className="text-sm text-ink-2">
            {approve
              ? `The invoice total of ${formatINR(run.total)} will count against ${run.matched_po ?? "its PO"}.`
              : "The invoice will not be paid and consumes no PO balance."}{" "}
            The automated decision stays on record next to yours. This cannot be changed later.
          </p>
          <label className="block">
            <span className="text-label uppercase text-ink-3">Note (required)</span>
            <textarea
              autoFocus
              required
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              maxLength={2000}
              placeholder={approve ? "e.g. Called vendor on the number on file, bank change confirmed" : "e.g. Sent back to vendor for a corrected invoice"}
              className="mt-1 w-full resize-y rounded-control border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-4 focus:border-accent-500 focus:shadow-focus focus:outline-none"
            />
          </label>
          {error && <p className="rounded-control bg-reject-50 px-3 py-2 text-sm text-reject-700">{error}</p>}
        </div>
        <footer className="flex justify-end gap-2 border-t border-line px-4 py-3">
          <Button variant="neutral" onClick={onClose}>
            Cancel
          </Button>
          <button
            type="submit"
            disabled={busy || note.trim() === ""}
            className={cx(
              "inline-flex h-8 items-center gap-1.5 rounded-control px-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50",
              approve ? "bg-approve-700 hover:bg-approve-800" : "bg-reject-600 hover:bg-reject-700",
            )}
          >
            {busy ? "Saving..." : approve ? "Confirm approval" : "Confirm rejection"}
          </button>
        </footer>
      </form>
    </dialog>
  );
}
