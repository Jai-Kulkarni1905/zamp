import { ExternalLink, FileText, ScanLine } from "lucide-react";
import { useState } from "react";
import type { StageView } from "../../lib/types";
import { Card, Chip, cx } from "../ui/primitives";

/** The original PDF in the browser's own viewer (no PDF library), sticky beside the stages on desktop. */
export function PdfPanel({ src, filename, ingest }: { src: string; filename: string; ingest: StageView | undefined }) {
  const [showOnMobile, setShowOnMobile] = useState(false);
  const pages = ingest?.payload["pages"];
  const scanned = ingest?.payload["is_scanned"] === true;
  return (
    <Card className="flex flex-col overflow-hidden lg:sticky lg:top-[72px] lg:h-[calc(100vh-88px)]">
      <header className="flex items-center gap-2 border-b border-line px-3 py-2">
        <FileText className="size-4 shrink-0 text-reject-600" aria-hidden />
        <span className="num min-w-0 flex-1 truncate text-sm font-medium text-ink">{filename}</span>
        {typeof pages === "number" && <Chip>{pages} pg</Chip>}
        {ingest && ingest.status !== "PENDING" && ingest.status !== "RUNNING" && (
          <Chip tone={scanned ? "WARN" : "neutral"}>
            {scanned ? (
              <>
                <ScanLine className="mr-1 size-3" aria-hidden /> Scanned
              </>
            ) : (
              "Text PDF"
            )}
          </Chip>
        )}
        <a href={src} target="_blank" rel="noreferrer" className="grid size-7 place-items-center rounded-control text-ink-3 hover:bg-sunken hover:text-ink" title="Open in a new tab">
          <ExternalLink className="size-4" aria-hidden />
          <span className="sr-only">Open PDF in a new tab</span>
        </a>
      </header>
      <button
        type="button"
        onClick={() => setShowOnMobile((v) => !v)}
        className="border-b border-line px-3 py-2 text-left text-sm font-semibold text-accent-700 lg:hidden"
      >
        {showOnMobile ? "Hide invoice" : "Show invoice"}
      </button>
      <div className={cx("min-h-0 flex-1 bg-sunken", showOnMobile ? "block h-[70vh]" : "hidden", "lg:block lg:h-auto")}>
        <iframe title={`Invoice ${filename}`} src={`${src}#view=FitH`} className="size-full border-0" />
      </div>
    </Card>
  );
}
