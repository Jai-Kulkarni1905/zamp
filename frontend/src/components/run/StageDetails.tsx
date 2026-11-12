// What each stage card shows when expanded. Payload shapes come from backend/app/pipeline/stages/*.

import { ArrowRight, Building2, CircleCheck, CircleX, Landmark, Receipt } from "lucide-react";
import { Link } from "react-router";
import { compareMoney, FIELD_LABELS, FLAG_LABELS, formatINR, formatPct, isNegative, ratio } from "../../lib/format";
import type { ExtractedFieldRow, Payload, POCandidate, POCard, RuleView, StageView, UnitPriceRow } from "../../lib/types";
import { RuleRow } from "./RuleList";
import { Chip, ConfidenceBar, cx, FieldBox, KeyValueRows, Label, ProgressBar, StatusPill } from "../ui/primitives";

const asArray = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
const asObj = <T,>(v: unknown): T | null => (v && typeof v === "object" ? (v as T) : null);
const str = (v: unknown): string => (v === null || v === undefined ? "" : String(v));

function Table({ head, children, className }: { head: string[]; children: React.ReactNode; className?: string }) {
  return (
    <div className={cx("overflow-x-auto rounded-card border border-line", className)}>
      <table className="w-full min-w-[480px] border-collapse text-left text-sm">
        <thead className="bg-sunken">
          <tr>
            {head.map((h, i) => (
              <th key={h} className={cx("px-3 py-2 text-label uppercase text-ink-3", i > 0 && "whitespace-nowrap")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
    </div>
  );
}

function Ingest({ p }: { p: Payload }) {
  return (
    <div className="space-y-2">
      <FieldBox
        items={[
          { label: "Pages", value: str(p.pages) },
          { label: "Text layer", value: p.is_scanned ? "None (scanned)" : `${str(p.text_chars)} chars` },
          { label: "Seen before", value: p.seen_before ? "Yes, same file" : "No" },
        ]}
      />
      <p className="num truncate text-xs text-ink-3" title={str(p.file_hash)}>
        SHA-256 {str(p.file_hash)}
      </p>
    </div>
  );
}

function Extract({ p }: { p: Payload }) {
  const fields = asArray<ExtractedFieldRow>(p.fields);
  const lines = asArray<Record<string, string | number | null>>(p.line_items);
  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-3">
        {p.source === "live" ? `Live call to ${str(p.model)}` : `Recorded extraction (${str(p.model) || "fixture"})`}, one LLM call per
        invoice. Fields below 0.70 confidence are highlighted.
      </p>
      <Table head={["Field", "Value", "Confidence", "Read from"]}>
        {fields.map((f) => (
          <tr key={f.field} className={cx(f.low_confidence && "bg-review-50")}>
            <td className="whitespace-nowrap px-3 py-2 text-ink-2">
              {FIELD_LABELS[f.field] ?? f.field}
              {f.required && <span className="ml-1 text-reject-600" title="Required">*</span>}
            </td>
            <td className="num px-3 py-2 text-ink">{f.value === null ? <span className="text-ink-4">not printed</span> : String(f.value)}</td>
            <td className="px-3 py-2">
              <ConfidenceBar value={f.confidence} />
            </td>
            <td className="max-w-[220px] truncate px-3 py-2 text-xs text-ink-3" title={f.source_text ?? ""}>
              {f.source_text ?? ""}
            </td>
          </tr>
        ))}
      </Table>
      {lines.length > 0 && (
        <Table head={["Line item", "Qty", "Unit price", "Amount"]}>
          {lines.map((l, i) => (
            <tr key={i}>
              <td className="px-3 py-2 text-ink">{str(l.description)}</td>
              <td className="num px-3 py-2 text-right">{str(l.qty)}</td>
              <td className="num px-3 py-2 text-right">{l.unit_price ? formatINR(str(l.unit_price)) : ""}</td>
              <td className="num px-3 py-2 text-right">{l.amount ? formatINR(str(l.amount)) : ""}</td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}

function Normalize({ p }: { p: Payload }) {
  const changes = asArray<{ field: string; raw: string | null; normalized: string | null }>(p.changes);
  if (changes.length === 0) return <p className="text-xs text-ink-3">Nothing needed normalizing.</p>;
  return (
    <Table head={["Field", "As read", "Normalized"]}>
      {changes.map((c, i) => (
        <tr key={`${c.field}-${i}`}>
          <td className="px-3 py-2 text-ink-2">{FIELD_LABELS[c.field] ?? c.field}</td>
          <td className="num px-3 py-2 text-ink-3">{c.raw ?? "none"}</td>
          <td className="num px-3 py-2 text-ink">
            <ArrowRight className="mr-1 inline size-3 text-ink-4" aria-hidden />
            {c.normalized ?? "none"}
          </td>
        </tr>
      ))}
    </Table>
  );
}

function MatchIcon({ ok }: { ok: boolean }) {
  return ok ? <CircleCheck className="inline size-3.5 text-approve-600" aria-label="matches" /> : <CircleX className="inline size-3.5 text-reject-600" aria-label="differs" />;
}

function Vendor({ p }: { p: Payload }) {
  const v = asObj<Record<string, string | number>>(p.vendor);
  const bank = asObj<{ invoice?: { account: string | null; ifsc: string | null }; master?: { account: string; ifsc: string }; account_matches?: boolean; ifsc_matches?: boolean; phone_on_file?: string }>(p.bank);
  const candidates = asArray<{ vendor_id: string; name: string; score: number }>(p.candidates);
  if (!v) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-ink-2">No vendor in the master matched. Closest names:</p>
        <KeyValueRows rows={candidates.map((c) => [`${c.name} (${c.vendor_id})`, `${c.score}`])} />
      </div>
    );
  }
  return (
    <div className="grid gap-3 2xl:grid-cols-2">
      <div className="rounded-card border border-line p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <Label className="flex items-center gap-1.5">
            <Building2 className="size-3.5" aria-hidden /> Vendor master
          </Label>
          <Chip tone="PASS">{v.method === "GSTIN" ? "GSTIN match" : `Name ${str(v.score)}`}</Chip>
        </div>
        <div className="mb-2 text-base font-semibold text-ink">{str(v.legal_name)}</div>
        <KeyValueRows
          rows={[
            ["Vendor ID", str(v.vendor_id)],
            ["GSTIN", str(v.gstin)],
            ["Status", <StatusPill key="s" status={v.status === "APPROVED" ? "PASS" : "FAIL"} label={str(v.status)} />],
            ["Phone on file", str(v.phone)],
          ]}
        />
      </div>
      <div className={cx("rounded-card border p-3", bank?.account_matches === false || bank?.ifsc_matches === false ? "border-reject-300 bg-reject-50" : "border-line")}>
        <Label className="mb-2 flex items-center gap-1.5">
          <Landmark className="size-3.5" aria-hidden /> Bank details
        </Label>
        {bank?.invoice ? (
          <div className="grid grid-cols-[auto_1fr_1fr] items-baseline gap-x-3 gap-y-2 text-sm [&>span]:whitespace-nowrap">
            <span />
            <Label>On invoice</Label>
            <Label>On file</Label>
            <span className="text-xs text-ink-3">Account</span>
            <span className="num">
              {bank.invoice.account ?? "none"} <MatchIcon ok={bank.account_matches !== false} />
            </span>
            <span className="num text-ink-2">{bank.master?.account}</span>
            <span className="text-xs text-ink-3">IFSC</span>
            <span className="num">
              {bank.invoice.ifsc ?? "none"} <MatchIcon ok={bank.ifsc_matches !== false} />
            </span>
            <span className="num text-ink-2">{bank.master?.ifsc}</span>
          </div>
        ) : (
          <p className="text-xs text-ink-3">The invoice shows no bank details; payment goes to the account on file.</p>
        )}
      </div>
    </div>
  );
}

export function POBox({ po, title = "Purchase order" }: { po: POCard; title?: string }) {
  const over = po.remaining_after !== null && isNegative(po.remaining_after);
  return (
    <div className="rounded-card border border-line p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <Label className="flex items-center gap-1.5">
          <Receipt className="size-3.5" aria-hidden /> {title}
        </Label>
        <div className="flex gap-1">
          {po.match_type && <Chip tone={po.match_type === "INFERRED" ? "WARN" : "PASS"}>{po.match_type === "INFERRED" ? "Inferred" : "On invoice"}</Chip>}
          <Chip>{po.status}</Chip>
        </div>
      </div>
      <div className="num mb-2 text-base font-semibold text-ink">{po.po_number}</div>
      <KeyValueRows
        rows={[
          ["PO total", formatINR(po.total)],
          ["Already consumed", formatINR(po.consumed)],
          ["Remaining before", formatINR(po.remaining)],
          ["This invoice", po.invoice_total ? formatINR(po.invoice_total) : "n/a"],
          ["Remaining after", <span key="ra" className={cx(over && "font-semibold text-review-700")}>{formatINR(po.remaining_after)}</span>],
        ]}
      />
    </div>
  );
}

function POMatch({ p }: { p: Payload }) {
  const po = asObj<POCard>(p.po);
  const candidates = asArray<POCandidate>(p.candidates);
  return (
    <div className="space-y-3">
      {po ? <POBox po={po} /> : <p className="text-sm text-ink-2">No PO matched{p.po_reference ? ` for reference ${str(p.po_reference)}` : ""}.</p>}
      {candidates.length > 0 && (
        <>
          <p className="text-xs text-ink-3">
            No PO number on the invoice. Open POs of this vendor were scored: 60% balance fit, 40% line description similarity.
            A clear winner needs at least 0.75 and a 0.15 lead.
          </p>
          <Table head={["PO", "Score", "Balance fit", "Description", "Remaining"]}>
            {candidates.map((c, i) => (
              <tr key={c.po_number} className={cx(i === 0 && po && "bg-approve-50")}>
                <td className="num px-3 py-2">{c.po_number}</td>
                <td className="num px-3 py-2 font-semibold">{c.score.toFixed(2)}</td>
                <td className="num px-3 py-2">{c.balance_fit.toFixed(2)}</td>
                <td className="num px-3 py-2">{c.description_similarity.toFixed(2)}</td>
                <td className="num px-3 py-2 text-right">{formatINR(c.remaining)}</td>
              </tr>
            ))}
          </Table>
        </>
      )}
    </div>
  );
}

function Amount({ p }: { p: Payload }) {
  const po = asObj<POCard>(p.po);
  const tolerance = str(p.tolerance);
  const overage = str(p.overage);
  const rows = asArray<UnitPriceRow>(p.unit_prices);
  if (!po) return <p className="text-sm text-ink-2">No PO matched, so there is nothing to compare against.</p>;
  const overTolerance = tolerance && overage ? compareMoney(overage, tolerance) > 0 : false;
  const used = tolerance && overage ? ratio(overage, tolerance) : 0;
  const hasOverage = overage !== "" && compareMoney(overage, "0") > 0;
  return (
    <div className="space-y-3">
      <FieldBox
        items={[
          { label: "PO remaining", value: formatINR(po.remaining), hint: `of ${formatINR(po.total)}` },
          { label: "This invoice", value: po.invoice_total ? formatINR(po.invoice_total) : "n/a" },
          {
            label: "Over remaining",
            value: <span className={cx(hasOverage && (overTolerance ? "text-reject-700" : "text-review-700"))}>{hasOverage ? formatINR(overage, { sign: true }) : "₹0.00"}</span>,
            hint: `Tolerance ${formatINR(tolerance)}`,
          },
        ]}
      />
      {hasOverage && (
        <div>
          <div className="mb-1 flex justify-between text-xs">
            <span className="text-ink-3">Tolerance used: max(2% of remaining, ₹500)</span>
            <span className="num text-ink-2">{overTolerance ? "exceeded" : `${formatPct(used, 0)} of ${formatINR(tolerance)}`}</span>
          </div>
          <ProgressBar value={used} tone={overTolerance ? "FAIL" : "WARN"} label="Tolerance used" />
        </div>
      )}
      {rows.length > 0 && (
        <Table head={["Invoice line", "Invoice unit", "PO unit", "Variance"]}>
          {rows.map((r, i) => (
            <tr key={i} className={cx(r.flagged && "bg-review-50")}>
              <td className="px-3 py-2">
                <div className="text-ink">{r.description}</div>
                {r.paired ? <div className="text-xs text-ink-3">PO line {r.po_line_no}: {r.paired}</div> : <div className="text-xs text-ink-3">No matching PO line</div>}
              </td>
              <td className="num px-3 py-2 text-right">{r.invoice_unit_price ? formatINR(r.invoice_unit_price) : ""}</td>
              <td className="num px-3 py-2 text-right">{r.po_unit_price ? formatINR(r.po_unit_price) : ""}</td>
              <td className={cx("num px-3 py-2 text-right", r.flagged ? "font-semibold text-review-700" : "text-ink-2")}>
                {r.variance_pct !== undefined ? `${r.variance_pct > 0 ? "+" : ""}${r.variance_pct.toFixed(1)}%` : ""}
              </td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}

function Duplicates({ p }: { p: Payload }) {
  const originals = asArray<{ run_id: string; filename: string }>(p.originals);
  return (
    <div className="space-y-2">
      <p className="text-xs text-ink-3">Compared against {str(p.compared_against)} earlier run(s): same file hash, same canonical invoice number, or near copy (total within ₹1, date within 7 days, number 85% similar).</p>
      {originals.map((o) => (
        <Link key={o.run_id} to={`/run/${o.run_id}`} className="inline-flex items-center gap-1.5 rounded-control border border-reject-300 bg-reject-50 px-2.5 py-1 text-sm font-semibold text-reject-700 hover:bg-reject-100">
          Original run: {o.filename} <ArrowRight className="size-3.5" aria-hidden />
        </Link>
      ))}
    </div>
  );
}

function Decide({ p }: { p: Payload }) {
  const flags = asArray<string>(p.flags);
  const hard = asArray<string>(p.hard_fails);
  const soft = asArray<string>(p.soft_fails);
  const review = asArray<string>(p.review_warnings);
  return (
    <div className="space-y-2">
      <FieldBox
        items={[
          { label: "Hard fails", value: hard.length ? hard.join(", ") : "none", hint: "any one rejects" },
          { label: "Soft fails", value: soft.length ? soft.join(", ") : "none", hint: "any one needs review" },
          { label: "Review warnings", value: review.length ? review.join(", ") : "none", hint: "any one needs review" },
        ]}
      />
      {flags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {flags.map((f) => (
            <Chip key={f} tone={f === "DUPLICATE" ? "FAIL" : "WARN"}>
              {FLAG_LABELS[f] ?? f}
            </Chip>
          ))}
        </div>
      )}
    </div>
  );
}

export function StageDetail({ stage, rules }: { stage: StageView; rules: RuleView[] }) {
  const p = stage.payload;
  if (stage.status === "PENDING" || stage.status === "RUNNING") {
    return <p className="text-xs text-ink-3">{stage.status === "RUNNING" ? "Working on it..." : "Waiting for earlier stages."}</p>;
  }
  if (stage.status === "SKIPPED" && rules.length === 0) return <p className="text-xs text-ink-3">{stage.message}</p>;
  const body = (() => {
    switch (stage.stage) {
      case "ingest":
        return <Ingest p={p} />;
      case "extract":
        return p.fields ? <Extract p={p} /> : <p className="text-sm text-reject-700">{stage.message}</p>;
      case "normalize":
        return <Normalize p={p} />;
      case "vendor":
        return <Vendor p={p} />;
      case "po_match":
        return <POMatch p={p} />;
      case "amount":
        return <Amount p={p} />;
      case "duplicates":
        return <Duplicates p={p} />;
      case "decide":
        return <Decide p={p} />;
      default:
        return null;
    }
  })();
  const showRules = !["decide", "explain"].includes(stage.stage) && rules.length > 0;
  return (
    <div className="space-y-3">
      {body}
      {showRules && (
        <div>
          <Label className="mb-1.5">Checks ({rules.filter((r) => r.outcome === "PASS").length} of {rules.filter((r) => r.outcome !== "SKIPPED").length} passed)</Label>
          <ul className="space-y-1.5">
            {rules.map((r) => (
              <RuleRow key={r.rule_id} rule={r} />
            ))}
          </ul>
        </div>
      )}
      {stage.stage === "explain" && <p className="text-xs text-ink-3">Built from the rule results by a template, so it cannot contradict the decision. See the decision card below.</p>}
    </div>
  );
}

