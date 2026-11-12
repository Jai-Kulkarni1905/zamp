// Formatting helpers. Money stays a string end to end: we only regroup digits, never go through float.

/** "177000.00" -> "₹1,77,000.00". Accepts negative values and missing decimals. */
export function formatINR(value: string | null | undefined, opts: { sign?: boolean } = {}): string {
  if (value === null || value === undefined || value === "") return "n/a";
  const trimmed = value.trim();
  const negative = trimmed.startsWith("-");
  const [intRaw = "0", fracRaw = ""] = trimmed.replace(/^[-+]/, "").split(".");
  const frac = (fracRaw + "00").slice(0, 2);
  const digits = intRaw.replace(/^0+(?=\d)/, "");
  let grouped = digits;
  if (digits.length > 3) {
    const head = digits.slice(0, -3);
    const tail = digits.slice(-3);
    grouped = head.replace(/\B(?=(\d{2})+(?!\d))/g, ",") + "," + tail;
  }
  const sign = negative ? "-" : opts.sign && !isZero(value) ? "+" : "";
  return `${sign}₹${grouped}.${frac}`;
}

export function isZero(value: string): boolean {
  return /^[-+]?0*(\.0*)?$/.test(value.trim());
}

export function isNegative(value: string | null | undefined): boolean {
  return !!value && value.trim().startsWith("-") && !isZero(value);
}

/** Compare two decimal strings without floats. */
export function compareMoney(a: string, b: string): number {
  const scale = (v: string) => {
    const neg = v.trim().startsWith("-");
    const [i = "0", f = ""] = v.trim().replace(/^[-+]/, "").split(".");
    const n = BigInt(i + (f + "00").slice(0, 2));
    return neg ? -n : n;
  };
  const d = scale(a) - scale(b);
  return d === 0n ? 0 : d > 0n ? 1 : -1;
}

/** Ratio of two decimal strings for progress bars only (display, not money math). */
export function ratio(part: string, whole: string): number {
  const w = Number(whole);
  if (!w) return 0;
  return Math.min(Math.max(Number(part) / w, 0), 1);
}

export function formatPct(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

const IST = "Asia/Kolkata";

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("en-IN", {
    timeZone: IST,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-IN", {
    timeZone: IST,
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function formatDate(isoDate: string | null | undefined): string {
  if (!isoDate) return "n/a";
  const [y, m, d] = isoDate.split("-").map(Number);
  if (!y || !m || !d) return isoDate;
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-IN", {
    timeZone: "UTC",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export const STAGE_LABELS: Record<string, string> = {
  ingest: "Ingest",
  extract: "Extract",
  normalize: "Normalize",
  validate: "Validate",
  vendor: "Vendor check",
  po_match: "PO match",
  amount: "Amount check",
  duplicates: "Duplicate check",
  decide: "Decide",
  explain: "Explain",
};

export const STAGE_HINTS: Record<string, string> = {
  ingest: "Hash, pages, text layer",
  extract: "Gemini reads the PDF into fields",
  normalize: "Dates, money, canonical numbers",
  validate: "Required fields, arithmetic, grounding, dates",
  vendor: "GSTIN or name, status, bank details",
  po_match: "Explicit reference or inferred",
  amount: "Against remaining PO balance",
  duplicates: "Same file, number, or near copy",
  decide: "Deterministic rules, no LLM",
  explain: "Template verdict and next actions",
};

export const FIELD_LABELS: Record<string, string> = {
  vendor_name: "Vendor name",
  vendor_gstin: "Vendor GSTIN",
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  due_date: "Due date",
  po_reference: "PO reference",
  currency: "Currency",
  subtotal: "Subtotal",
  tax_inclusive: "Tax inclusive",
  total: "Total",
  bank_account: "Bank account",
  ifsc: "IFSC",
};

export const FLAG_LABELS: Record<string, string> = {
  FRAUD_RISK: "Fraud risk",
  PO_INFERRED: "PO inferred",
  LOW_CONFIDENCE: "Low confidence",
  OVER_PO: "Over PO",
  DUPLICATE: "Duplicate",
};

export const DECISION_LABELS: Record<string, string> = {
  APPROVED: "Approved",
  NEEDS_REVIEW: "Needs review",
  REJECTED: "Rejected",
};
