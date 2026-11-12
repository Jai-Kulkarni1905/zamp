import { FileUp, LoaderCircle } from "lucide-react";
import { useState, type DragEvent } from "react";
import { useNavigate } from "react-router";
import { api } from "../lib/api";
import { cx } from "./ui/primitives";

const MAX_MB = 15;

/** Drop a PDF, upload it, go straight to its live run view. */
export function Dropzone({ compact = false }: { compact?: boolean }) {
  const navigate = useNavigate();
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    if (!file.name.toLowerCase().endsWith(".pdf") && file.type !== "application/pdf") {
      setError("Please choose a PDF file.");
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`The file is larger than ${MAX_MB} MB.`);
      return;
    }
    setBusy(true);
    try {
      const created = await api.upload(file);
      navigate(`/run/${created.run_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  const onDrop = (e: DragEvent<HTMLElement>) => {
    e.preventDefault();
    setDragging(false);
    void send(e.dataTransfer.files[0]);
  };

  return (
    <div>
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cx(
          "flex cursor-pointer items-center gap-3 rounded-card border-2 border-dashed transition-colors",
          compact ? "h-full min-h-[84px] px-4 py-3" : "flex-col justify-center px-6 py-14 text-center",
          dragging ? "border-accent-500 bg-accent-50" : "border-line bg-sunken hover:border-line-strong",
          busy && "pointer-events-none opacity-70",
        )}
      >
        <span className="grid size-10 shrink-0 place-items-center rounded-control bg-surface text-accent-600 shadow-card">
          {busy ? <LoaderCircle className="size-5 animate-spin" aria-hidden /> : <FileUp className="size-5" aria-hidden />}
        </span>
        <span className={cx("min-w-0", !compact && "space-y-1")}>
          <span className="block text-sm font-semibold text-ink">{busy ? "Uploading..." : "Drop an invoice PDF, or click to choose"}</span>
          <span className="block text-xs text-ink-3">Up to {MAX_MB} MB, text or scanned. Opens the live run view.</span>
        </span>
        <input type="file" accept="application/pdf,.pdf" className="sr-only" onChange={(e) => void send(e.target.files?.[0])} />
      </label>
      {error && <p className="mt-2 rounded-control border border-reject-300 bg-reject-50 px-3 py-2 text-sm text-reject-700">{error}</p>}
    </div>
  );
}
