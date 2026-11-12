# Demo script

Exact run order for the live demo and the 5 minute video. The order matters: EC-1-C needs A and B approved
first, and EC-2 needs HP-1 approved first (PLAN.md section 7).

## Before you start (5 minutes ahead)

1. Open the app URL. If it is asleep, the first load takes about a minute.
2. Reset to an empty dashboard:
   `curl -X POST https://<app>/api/admin/reset -H "X-Admin-Token: <token>"`
3. Check the dashboard shows 0 runs, the badge reads **Live Gemini**, and the review queue is empty.
4. Have the 8 PDFs from `data/invoices/` in one folder, ready to drag.
5. Optional dry run: `python scripts/rehearse.py --base-url https://<app> --admin-token <token>`, then reset again.

## Run order

| # | Drop | Expected | What to show and say |
|---|---|---|---|
| 1 | `HP-1.pdf` | APPROVED | Stages light up live. Open Extract: fields with confidence. Vendor matched by GSTIN, PO-2026-0101 found, amount within balance. "The LLM only extracts. Rules decide. A template explains." |
| 2 | `HP-2.pdf` | APPROVED | Different layout, prices include GST. Amount stage: "within tolerance", 1.5% over PO, tolerance bar. |
| 3 | `EC-1-A.pdf` | APPROVED | Split PO ₹3,00,000. Back on the dashboard: Purchase orders tab, ₹1,20,000 consumed. |
| 4 | `EC-1-B.pdf` | APPROVED | Dashboard: PO-2026-0103 at 80%, ₹60,000 left. |
| 5 | `EC-1-C.pdf` | NEEDS_REVIEW, OVER_PO | "Exceeds remaining ₹60,000.00 by ₹30,000.00." Unit price +50% vs milestone 3. Next action: amend the PO or get a revised invoice. |
| 6 | `EC-2.pdf` | REJECTED, DUPLICATE | Same invoice re-sent with a new layout and `INV/2026/0142` instead of `INV-2026-142`. Duplicate stage links the original HP-1 run. Only action: do not pay. |
| 7 | `EC-3.pdf` | NEEDS_REVIEW, LOW_CONFIDENCE, PO_INFERRED | Scanned, rotated image: Ingest says "scanned", grounding skipped. No invoice number, no PO: PO-2026-0104 inferred over the office chairs PO (scores shown). Next actions list exactly what is missing. |
| 8 | `EC-4.pdf` | NEEDS_REVIEW, FRAUD_RISK | Approved vendor, valid PO, but the bank account and IFSC changed. "Verify by calling the number on file, not the one on the invoice." |

## Close (review queue)

9. Dashboard > **Review queue** (3). Open EC-4 from the queue: "Queue: 3 of 3".
10. **Approve** with a note, e.g. "Called +91 40 6712 5500, bank change confirmed". Show the banner leads with
    the reviewer decision and the automated verdict is kept.
11. Back on the dashboard: review queue 2, PO-2026-0106 consumed. KPIs: approval rate, value processed.

## 5 minute video outline

| Time | Beat |
|---|---|
| 0:00 to 0:30 | Problem: AP teams check every invoice against vendor master, POs and history by hand. Design rule: the LLM extracts, rules decide, templates explain. |
| 0:30 to 1:30 | HP-1 live: every stage visible, extraction with confidence, deterministic checks, decision card. |
| 1:30 to 2:30 | Split PO (EC-1 A, B, C) with the PO tab between drops. |
| 2:30 to 3:15 | Disguised duplicate (EC-2). |
| 3:15 to 4:00 | Scanned invoice with missing data (EC-3), then bank change (EC-4). |
| 4:00 to 4:40 | Review queue: approve EC-4 with a note, dashboard updates. |
| 4:40 to 5:00 | Wrap: auditable (every rule stored), reproducible (same input, same decision), one LLM call per invoice. |

## Likely questions

- **Why not let the LLM decide?** Auditability and reproducibility: every decision is a stored rule result
  with evidence, and the same input always gives the same answer. The explanation is a template, so it cannot
  contradict the decision.
- **What if Gemini misreads a field?** Confidence below 0.70 and grounding (the value must appear in the PDF
  text) send it to review. Missing required fields are never guessed.
- **Cost?** One Gemini call per new invoice, cached by file hash.
- **Thresholds?** All in `docs/assumptions.md` with the reasoning (tolerance max(2%, ₹500), 180 days, fuzzy 90).
