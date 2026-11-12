import { Plus, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../lib/api";
import { addMoney, cleanDecimal, compareMoney, formatINR, mulMoney } from "../../lib/format";
import type { POView, Vendor } from "../../lib/types";
import { Button, Chip, cx, Label } from "../ui/primitives";

interface LineDraft {
  key: number;
  description: string;
  hsn_sac: string;
  qty: string;
  unit: string;
  unit_price: string;
}

const control =
  "h-8 w-full rounded-control border border-line bg-surface px-2 text-sm text-ink placeholder:text-ink-4 focus:border-accent-500 focus:shadow-focus focus:outline-none";

let nextKey = 1;
const emptyLine = (): LineDraft => ({ key: nextKey++, description: "", hsn_sac: "", qty: "", unit: "", unit_price: "" });

function todayIST(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }); // YYYY-MM-DD
}

/**
 * New purchase order. The PO number is assigned by the server (shown here in advance); every other
 * field is typed in by the user (A66). Line amounts and the subtotal are previews only.
 */
export function NewPODialog({ vendors, onClose, onCreated }: { vendors: Vendor[]; onClose: () => void; onCreated: (po: POView) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [number, setNumber] = useState<string | null>(null);
  const [vendorId, setVendorId] = useState("");
  const [issueDate, setIssueDate] = useState("");
  const [lines, setLines] = useState<LineDraft[]>([emptyLine()]);
  const [total, setTotal] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    ref.current?.showModal();
    api.nextPONumber().then((r) => setNumber(r.po_number), () => setNumber(null));
  }, []);

  const setLine = (key: number, patch: Partial<LineDraft>) =>
    setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  const amounts = lines.map((l) => {
    const q = cleanDecimal(l.qty);
    const p = cleanDecimal(l.unit_price);
    return q !== null && p !== null ? mulMoney(q, p) : null;
  });
  const subtotal = amounts.every((a) => a !== null) ? addMoney(amounts as string[]) : null;
  const totalClean = cleanDecimal(total);

  const problems = useMemo(() => {
    const out: string[] = [];
    if (!vendorId) out.push("Choose a vendor");
    if (!issueDate) out.push("Enter the issue date");
    else if (issueDate > todayIST()) out.push("Issue date cannot be in the future");
    lines.forEach((l, i) => {
      const n = i + 1;
      if (!l.description.trim()) out.push(`Line ${n}: description`);
      if (!l.unit.trim()) out.push(`Line ${n}: unit`);
      const q = cleanDecimal(l.qty);
      if (q === null || compareMoney(q, "0") <= 0) out.push(`Line ${n}: quantity above 0`);
      const p = cleanDecimal(l.unit_price);
      if (p === null || compareMoney(p, "0") <= 0) out.push(`Line ${n}: unit price above 0`);
    });
    if (totalClean === null || compareMoney(totalClean, "0") <= 0) out.push("Enter the total including GST");
    else if (subtotal !== null && compareMoney(totalClean, subtotal) < 0) out.push("Total cannot be less than the line items");
    return out;
  }, [vendorId, issueDate, lines, totalClean, subtotal]);

  const submit = async () => {
    if (problems.length) return;
    setBusy(true);
    setError(null);
    try {
      const po = await api.createPO({
        vendor_id: vendorId,
        issue_date: issueDate,
        currency: "INR",
        total_amount: totalClean!,
        lines: lines.map((l) => ({
          description: l.description.trim(),
          hsn_sac: l.hsn_sac.trim(),
          qty: cleanDecimal(l.qty)!,
          unit: l.unit.trim(),
          unit_price: cleanDecimal(l.unit_price)!,
        })),
      });
      onCreated(po);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  const gstHint = subtotal ? `With 18% GST: ${formatINR(mulMoney(subtotal, "1.18"))}` : null;

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      className="m-auto w-[min(96vw,820px)] rounded-panel border border-line bg-surface p-0 text-ink shadow-raised backdrop:bg-ink/30"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <header className="flex items-center gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold">New purchase order</h2>
            <p className="text-xs text-ink-3">The PO number is assigned automatically. Fill in everything else.</p>
          </div>
          {number && <Chip className="text-xs">{number}</Chip>}
          <button type="button" onClick={onClose} className="grid size-7 place-items-center rounded-control text-ink-3 hover:bg-sunken" aria-label="Close">
            <X className="size-4" />
          </button>
        </header>

        <div className="max-h-[70vh] space-y-4 overflow-y-auto px-4 py-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]">
            <label className="flex flex-col gap-1">
              <Label>Vendor</Label>
              <select className={control} value={vendorId} onChange={(e) => setVendorId(e.target.value)} required>
                <option value="">Choose a vendor</option>
                {vendors.map((v) => (
                  <option key={v.vendor_id} value={v.vendor_id} disabled={v.status !== "APPROVED"}>
                    {v.legal_name} ({v.vendor_id}){v.status !== "APPROVED" ? ", blocked" : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <Label>Issue date</Label>
              <input type="date" className={control} value={issueDate} max={todayIST()} onChange={(e) => setIssueDate(e.target.value)} required />
            </label>
            <div className="flex flex-col gap-1">
              <Label>Currency</Label>
              <div className="flex h-8 items-center rounded-control border border-line bg-sunken px-2 text-sm text-ink-2">INR</div>
            </div>
          </div>

          <div>
            <Label className="mb-1.5">Line items</Label>
            <div className="space-y-2">
              <div className="hidden grid-cols-[minmax(0,3fr)_minmax(0,1fr)_minmax(0,0.8fr)_minmax(0,0.9fr)_minmax(0,1.2fr)_minmax(0,1.2fr)_32px] gap-2 px-0.5 md:grid">
                {["Description", "HSN/SAC", "Qty", "Unit", "Unit price (₹)", "Amount", ""].map((h) => (
                  <span key={h} className="text-label uppercase text-ink-4">
                    {h}
                  </span>
                ))}
              </div>
              {lines.map((l, i) => (
                <div
                  key={l.key}
                  className="grid grid-cols-2 gap-2 rounded-card border border-line p-2 md:grid-cols-[minmax(0,3fr)_minmax(0,1fr)_minmax(0,0.8fr)_minmax(0,0.9fr)_minmax(0,1.2fr)_minmax(0,1.2fr)_32px] md:items-center md:border-0 md:p-0"
                >
                  <input aria-label={`Line ${i + 1} description`} placeholder="Description" className={cx(control, "col-span-2 md:col-span-1")} value={l.description} onChange={(e) => setLine(l.key, { description: e.target.value })} />
                  <input aria-label={`Line ${i + 1} HSN/SAC`} placeholder="HSN/SAC" className={control} value={l.hsn_sac} maxLength={16} onChange={(e) => setLine(l.key, { hsn_sac: e.target.value })} />
                  <input aria-label={`Line ${i + 1} quantity`} placeholder="Qty" inputMode="decimal" className={cx(control, "num text-right")} value={l.qty} onChange={(e) => setLine(l.key, { qty: e.target.value })} />
                  <input aria-label={`Line ${i + 1} unit`} placeholder="Unit" className={control} value={l.unit} maxLength={16} onChange={(e) => setLine(l.key, { unit: e.target.value })} />
                  <input aria-label={`Line ${i + 1} unit price`} placeholder="Unit price" inputMode="decimal" className={cx(control, "num text-right")} value={l.unit_price} onChange={(e) => setLine(l.key, { unit_price: e.target.value })} />
                  <span className="num self-center text-right text-sm text-ink-2">{amounts[i] ? formatINR(amounts[i]) : ""}</span>
                  <button
                    type="button"
                    onClick={() => setLines((prev) => prev.filter((x) => x.key !== l.key))}
                    disabled={lines.length === 1}
                    className="grid size-8 place-items-center justify-self-end rounded-control text-ink-3 hover:bg-reject-50 hover:text-reject-600 disabled:opacity-30"
                    aria-label={`Remove line ${i + 1}`}
                  >
                    <Trash2 className="size-4" />
                  </button>
                </div>
              ))}
            </div>
            <Button variant="ghost" icon={Plus} className="mt-2" onClick={() => setLines((prev) => [...prev, emptyLine()])}>
              Add line
            </Button>
          </div>

          <div className="grid grid-cols-1 gap-3 rounded-card bg-sunken p-3 sm:grid-cols-2 sm:items-end">
            <div>
              <Label>Line items subtotal</Label>
              <div className="num mt-1 text-base font-semibold">{subtotal ? formatINR(subtotal) : "..."}</div>
              {gstHint && <div className="mt-0.5 text-xs text-ink-3">{gstHint}</div>}
            </div>
            <label className="flex flex-col gap-1">
              <Label>Total including GST (₹)</Label>
              <input inputMode="decimal" placeholder="e.g. 114460.00" className={cx(control, "num text-right")} value={total} onChange={(e) => setTotal(e.target.value)} required />
              <span className="text-xs text-ink-3">The maximum the vendor can bill against this PO.</span>
            </label>
          </div>

          {error && <p className="rounded-control bg-reject-50 px-3 py-2 text-sm text-reject-700">{error}</p>}
        </div>

        <footer className="flex flex-col-reverse gap-2 border-t border-line px-4 py-3 sm:flex-row sm:items-center">
          <p className="flex-1 text-xs text-ink-3">{problems.length ? `Still needed: ${problems.slice(0, 2).join("; ")}${problems.length > 2 ? "..." : ""}` : "Ready to create."}</p>
          <Button variant="neutral" onClick={onClose}>
            Cancel
          </Button>
          <button
            type="submit"
            disabled={busy || problems.length > 0}
            className="inline-flex h-8 items-center justify-center gap-1.5 rounded-control bg-approve-700 px-3 text-sm font-semibold text-white hover:bg-approve-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Creating..." : `Create ${number ?? "purchase order"}`}
          </button>
        </footer>
      </form>
    </dialog>
  );
}
