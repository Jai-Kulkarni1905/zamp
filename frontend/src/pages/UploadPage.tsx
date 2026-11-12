import { FileUp, LoaderCircle } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { useNavigate } from "react-router";
import { Card, cx } from "../components/ui/primitives";
import { api } from "../lib/api";

const MAX_MB = 15;

/** Minimal upload page: drop a PDF, go straight to its live run view. The full dashboard is Layer 5. */
export function UploadPage() {
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
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
    <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6 sm:py-16">
      <h1 className="text-lg font-semibold text-ink">Process an invoice</h1>
      <p className="mt-1 text-sm text-ink-3">
        Drop a vendor invoice PDF. Each stage runs live: Gemini extracts, deterministic rules decide, a template explains.
      </p>
      <Card className="mt-5 p-2">
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cx(
            "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-card border-2 border-dashed px-6 py-14 text-center transition-colors",
            dragging ? "border-accent-500 bg-accent-50" : "border-line bg-sunken hover:border-line-strong",
            busy && "pointer-events-none opacity-70",
          )}
        >
          <span className="grid size-12 place-items-center rounded-panel bg-surface text-accent-600 shadow-card">
            {busy ? <LoaderCircle className="size-6 animate-spin" aria-hidden /> : <FileUp className="size-6" aria-hidden />}
          </span>
          <span className="text-base font-semibold text-ink">{busy ? "Uploading..." : "Drag a PDF here, or click to choose"}</span>
          <span className="text-xs text-ink-3">PDF up to {MAX_MB} MB. Text or scanned.</span>
          <input
            ref={input}
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            onChange={(e) => void send(e.target.files?.[0])}
          />
        </label>
      </Card>
      {error && <p className="mt-3 rounded-control border border-reject-300 bg-reject-50 px-3 py-2 text-sm text-reject-700">{error}</p>}
    </div>
  );
}
