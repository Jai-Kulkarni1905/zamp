import { ChevronDown } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router";
import { compareMoney, formatINR, formatPct, isNegative, ratio } from "../../lib/format";
import type { POView } from "../../lib/types";
import { Chip, cx, ProgressBar, StatusPill } from "../ui/primitives";

/** Consumption tone: accent while within the PO, amber when over (only possible within tolerance), neutral when closed. */
function tone(po: POView): string {
  if (po.status !== "OPEN") return "SKIPPED";
  if (isNegative(po.remaining)) return "WARN";
  return "running";
}

function Consumption({ po }: { po: POView }) {
  const used = ratio(po.consumed, po.total);
  const over = isNegative(po.remaining);
  return (
    <div className="min-w-[110px]">
      <ProgressBar value={over ? 1 : used} tone={tone(po)} label={`${po.po_number} consumed`} />
      <div className={cx("num mt-1 text-[11px]", over ? "font-semibold text-review-700" : "text-ink-3")}>
        {over ? `over by ${formatINR(po.remaining.replace("-", ""))}` : `${formatPct(used, 0)} used`}
      </div>
    </div>
  );
}

function Lines({ po }: { po: POView }) {
  if (po.lines.length === 0) return null;
  return (
    <div className="mb-3">
      <div className="mb-1 text-label uppercase text-ink-3">Ordered</div>
      <ul className="divide-y divide-line rounded-card border border-line bg-surface">
        {po.lines.map((l) => (
          <li key={l.line_no} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-3 py-1.5 text-sm">
            <span className="min-w-0 flex-1 text-ink">{l.description}</span>
            <span className="num text-ink-3">
              {l.qty.replace(/\.0+$/, "")} {l.unit} x {formatINR(l.unit_price)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Invoices({ po }: { po: POView }) {
  if (po.invoices.length === 0)
    return (
      <>
        <Lines po={po} />
        <p className="text-xs text-ink-3">No invoices matched to this PO yet.</p>
      </>
    );
  return (
    <>
    <Lines po={po} />
    <div className="mb-1 text-label uppercase text-ink-3">Invoices</div>
    <ul className="divide-y divide-line rounded-card border border-line bg-surface">
      {po.invoices.map((inv) => (
        <li key={inv.run_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
          <Link to={`/run/${inv.run_id}`} className="num min-w-0 flex-1 truncate font-medium text-accent-700 hover:underline">
            {inv.invoice_number ?? inv.filename}
          </Link>
          <span className="num text-ink">{inv.total ? formatINR(inv.total) : ""}</span>
          <StatusPill status={inv.effective_decision ?? "PENDING"} />
          <Chip tone={inv.counts_against_po ? "PASS" : "neutral"}>{inv.counts_against_po ? "counts" : "not counted"}</Chip>
        </li>
      ))}
    </ul>
    </>
  );
}

export function POTable({ pos, highlight = null }: { pos: POView[]; highlight?: string | null }) {
  const [open, setOpen] = useState<string | null>(highlight);
  // A just-created PO opens itself so it is visible straight away.
  useEffect(() => {
    if (!highlight) return;
    setOpen(highlight);
    // New POs sort to the end of the list: bring the row into view.
    window.setTimeout(() => document.getElementById(`po-${highlight}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
  }, [highlight]);
  const toggle = (po: string) => setOpen((cur) => (cur === po ? null : po));
  return (
    <>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="bg-sunken">
            <tr className="text-label uppercase text-ink-3">
              <th className="px-4 py-2.5">PO</th>
              <th className="px-3 py-2.5">Vendor</th>
              <th className="px-3 py-2.5 text-right">Total</th>
              <th className="px-3 py-2.5 text-right">Consumed</th>
              <th className="px-3 py-2.5 text-right">Remaining</th>
              <th className="px-3 py-2.5">Consumption</th>
              <th className="px-3 py-2.5 text-right">Invoices</th>
              <th className="w-8 px-2 py-2.5"><span className="sr-only">Expand</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {pos.map((po) => {
              const isOpen = open === po.po_number;
              return (
                <Fragment key={po.po_number}>
                  <tr
                    id={`po-${po.po_number}`}
                    onClick={() => toggle(po.po_number)}
                    className={cx("cursor-pointer align-top hover:bg-sunken", isOpen && "bg-sunken", highlight === po.po_number && "bg-approve-50")}
                    aria-expanded={isOpen}
                  >
                    <td className="whitespace-nowrap px-4 py-3">
                      <div className="num font-medium text-ink">{po.po_number}</div>
                      <Chip tone={po.status === "OPEN" ? "neutral" : "SKIPPED"} className="mt-1">
                        {po.status}
                      </Chip>
                    </td>
                    <td className="max-w-[200px] px-3 py-3">
                      <div className="truncate text-ink">{po.vendor_name}</div>
                      <div className="num text-xs text-ink-4">{po.vendor_id}</div>
                    </td>
                    <td className="num whitespace-nowrap px-3 py-3 text-right">{formatINR(po.total)}</td>
                    <td className="num whitespace-nowrap px-3 py-3 text-right">{formatINR(po.consumed)}</td>
                    <td
                      className={cx(
                        "num whitespace-nowrap px-3 py-3 text-right font-semibold",
                        isNegative(po.remaining) ? "text-review-700" : compareMoney(po.remaining, "0") === 0 ? "text-ink-3" : "text-ink",
                      )}
                    >
                      {formatINR(po.remaining)}
                    </td>
                    <td className="px-3 py-3">
                      <Consumption po={po} />
                    </td>
                    <td className="num px-3 py-3 text-right text-ink-2">{po.invoices.length}</td>
                    <td className="px-2 py-3">
                      <ChevronDown className={cx("size-4 text-ink-4 transition-transform", isOpen && "rotate-180")} aria-hidden />
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="bg-sunken">
                      <td colSpan={8} className="px-4 pb-4">
                        <Invoices po={po} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <ul className="divide-y divide-line md:hidden">
        {pos.map((po) => (
          <li key={po.po_number} className="space-y-2 px-4 py-3">
            <button type="button" onClick={() => toggle(po.po_number)} className="flex w-full items-start justify-between gap-2 text-left">
              <span className="min-w-0">
                <span className="num block font-medium text-ink">{po.po_number}</span>
                <span className="block truncate text-xs text-ink-3">{po.vendor_name}</span>
              </span>
              <span className="text-right">
                <span className={cx("num block font-semibold", isNegative(po.remaining) ? "text-review-700" : "text-ink")}>
                  {formatINR(po.remaining)}
                </span>
                <span className="num block text-[11px] text-ink-3">left of {formatINR(po.total)}</span>
              </span>
            </button>
            <Consumption po={po} />
            {open === po.po_number && <Invoices po={po} />}
          </li>
        ))}
      </ul>
    </>
  );
}
