import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api } from "../../lib/api";
import { cx } from "../ui/primitives";

/**
 * "Queue: 2 of 3  < >" for working through the review queue, like the reference's queue pager.
 * Re-reads the queue whenever the run changes, so a just-reviewed run drops out and "Next" moves on.
 */
export function QueueNav({ runId, version }: { runId: string; version: string }) {
  const [ids, setIds] = useState<string[] | null>(null);

  useEffect(() => {
    let alive = true;
    api.runs({ review_queue: true }).then(
      (r) => alive && setIds(r.items.map((i) => i.id).reverse()), // oldest first: work the queue in arrival order
      () => alive && setIds([]),
    );
    return () => {
      alive = false;
    };
  }, [runId, version]);

  if (ids === null) return null;
  const at = ids.indexOf(runId);
  const link = (id: string | undefined) => (id ? `/run/${id}?queue=review` : undefined);

  if (at === -1) {
    return ids.length ? (
      <Link to={link(ids[0])!} className="inline-flex h-8 items-center gap-1 rounded-control border border-accent-200 bg-accent-50 px-2.5 text-sm font-semibold text-accent-800 hover:bg-accent-100">
        Next in queue ({ids.length}) <ChevronRight className="size-4" aria-hidden />
      </Link>
    ) : (
      <Link to="/" className="inline-flex h-8 items-center rounded-control border border-approve-300 bg-approve-50 px-2.5 text-sm font-semibold text-approve-800">
        Review queue is clear
      </Link>
    );
  }

  const prev = link(ids[at - 1]);
  const next = link(ids[at + 1]);
  const arrow = "grid size-6 place-items-center rounded-chip text-ink-2";
  return (
    <span className="inline-flex h-8 items-center gap-1 rounded-control border border-line bg-surface pr-1 pl-2.5 text-xs text-ink-3">
      Queue: <span className="num font-semibold text-ink">{at + 1}</span> of <span className="num font-semibold text-ink">{ids.length}</span>
      {prev ? (
        <Link to={prev} className={cx(arrow, "hover:bg-sunken")} aria-label="Previous in queue">
          <ChevronLeft className="size-4" />
        </Link>
      ) : (
        <span className={cx(arrow, "opacity-30")} aria-hidden>
          <ChevronLeft className="size-4" />
        </span>
      )}
      {next ? (
        <Link to={next} className={cx(arrow, "hover:bg-sunken")} aria-label="Next in queue">
          <ChevronRight className="size-4" />
        </Link>
      ) : (
        <span className={cx(arrow, "opacity-30")} aria-hidden>
          <ChevronRight className="size-4" />
        </span>
      )}
    </span>
  );
}
