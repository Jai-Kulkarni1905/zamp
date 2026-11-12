import { ChevronRight } from "lucide-react";
import { Link, useParams } from "react-router";
import { DecisionBanner } from "../components/run/DecisionBanner";
import { DecisionSection } from "../components/run/DecisionSection";
import { PdfPanel } from "../components/run/PdfPanel";
import { ReviewActions } from "../components/run/ReviewActions";
import { StageTimeline } from "../components/run/StageTimeline";
import { Card, Chip } from "../components/ui/primitives";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import { useRun } from "../lib/useRun";

export function RunPage() {
  const { id = "" } = useParams();
  const { run, stages, events, live, error, setRun } = useRun(id);

  if (!run) {
    return (
      <div className="mx-auto max-w-[1440px] px-4 py-10 sm:px-6">
        <Card className="p-6 text-sm text-ink-2">{error ? `Could not load run: ${error}` : "Loading run..."}</Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1440px] space-y-4 px-4 py-4 sm:px-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <nav aria-label="Breadcrumb" className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5 text-sm text-ink-3">
          <Link to="/" className="hover:text-ink">
            Runs
          </Link>
          {run.vendor_name && (
            <>
              <ChevronRight className="size-3.5" aria-hidden />
              <span className="truncate">{run.vendor_name}</span>
            </>
          )}
          <ChevronRight className="size-3.5" aria-hidden />
          <span className="num rounded-chip bg-sunken px-1.5 py-0.5 font-medium text-ink">{run.invoice_number ?? run.filename}</span>
          {run.invoice_date && <Chip>{formatDate(run.invoice_date)}</Chip>}
          {run.matched_po && <Chip tone={run.po_match_type === "INFERRED" ? "WARN" : "neutral"}>{run.matched_po}</Chip>}
        </nav>
        <ReviewActions run={run} onDone={setRun} />
      </div>

      {error && <p className="rounded-control border border-review-300 bg-review-50 px-3 py-2 text-sm text-review-800">{error}</p>}

      <DecisionBanner run={run} stages={stages} live={live} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <PdfPanel src={api.fileUrl(run.id)} filename={run.filename} ingest={stages.find((s) => s.stage === "ingest")} />
        <StageTimeline stages={stages} rules={run.rules} live={live} />
      </div>

      <DecisionSection run={run} events={events} />
    </div>
  );
}
