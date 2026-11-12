# Assumptions

Every assumption the AP Invoice Agent relies on. Each one has an ID (A1, A2, ...) so code, tests
and the interview can point to it. Rule IDs refer to `docs/process-map.md`.

If a number here changes, change it in `backend/app/config.py` (or the rules module) and here,
in the same commit.

## Threshold summary

| Name | Value | Used by |
|---|---|---|
| Scanned PDF detection | fewer than 50 extractable characters per page on average | ING-SCANNED |
| Arithmetic tolerance | ±₹1.00 | VAL-ARITH-LINES, VAL-ARITH-TOTAL |
| Low confidence | field confidence < 0.70 | VAL-CONFIDENCE |
| Max invoice age | 180 days before processing date | VAL-DATE-STALE |
| Vendor name fuzzy match | score ≥ 90 (0 to 100) | VEN-MATCH |
| PO inference: minimum score | ≥ 0.75 | PO-INFER |
| PO inference: winning margin | best minus second best ≥ 0.15 | PO-INFER |
| Amount tolerance over remaining PO balance | max(2% of remaining balance, ₹500) | AMT-REMAINING |
| Unit price variance vs PO | > 5% | AMT-UNIT-PRICE |
| PO line matching (for unit price) | description similarity ≥ 80 | AMT-UNIT-PRICE |
| Fuzzy duplicate: total | within ±₹1.00 | DUP-FUZZY |
| Fuzzy duplicate: date | within 7 days | DUP-FUZZY |
| Fuzzy duplicate: invoice number similarity | ≥ 85 | DUP-FUZZY |

## Severity summary

| Rule | Outcome when triggered | Severity | Review reason | Flag |
|---|---|---|---|---|
| VAL-REQUIRED (required field missing) | FAIL | SOFT | yes | LOW_CONFIDENCE |
| VAL-CONFIDENCE (confidence < 0.70) | WARN | SOFT | yes | LOW_CONFIDENCE |
| VAL-GROUNDING (value not in PDF text) | WARN | SOFT | yes | LOW_CONFIDENCE |
| VAL-ARITH-LINES / VAL-ARITH-TOTAL | FAIL | SOFT | yes | |
| VAL-DATE-FUTURE | FAIL | SOFT | yes | |
| VAL-DATE-STALE (older than 180 days) | WARN | SOFT | yes | |
| VAL-DUE-DATE (due before invoice date) | WARN | INFO | no | |
| VAL-GSTIN-FORMAT | WARN | SOFT | yes | |
| VAL-CURRENCY (not INR) | FAIL | SOFT | yes | |
| VEN-MATCH (vendor not found) | FAIL | SOFT | yes | |
| VEN-GSTIN (name matches, GSTIN differs) | WARN | SOFT | yes | |
| VEN-STATUS (vendor BLOCKED) | FAIL | HARD | n/a | |
| VEN-BANK (bank or IFSC differs) | FAIL | SOFT | yes | FRAUD_RISK |
| VEN-BANK-MISSING (no bank details on invoice) | WARN | INFO | no | |
| PO-EXPLICIT (PO not found, other vendor, or CLOSED) | FAIL | SOFT | yes | |
| PO-INFER (PO inferred, clear winner) | WARN | SOFT | yes | PO_INFERRED |
| PO-INFER (no clear winner) | FAIL | SOFT | yes | |
| AMT-REMAINING (over tolerance) | FAIL | SOFT | yes | OVER_PO |
| AMT-UNIT-PRICE (> 5% variance) | WARN | INFO | no | |
| DUP-HASH / DUP-NUMBER / DUP-FUZZY | FAIL | HARD | n/a | DUPLICATE |

"Review reason" means the WARN counts toward NEEDS_REVIEW. A WARN that is not a review reason is
still stored and shown, but on its own it cannot stop an approval.

## General

**A1. Currency is INR.** Every vendor and PO is in INR. An invoice in another currency fails
VAL-CURRENCY (SOFT). We do not convert currencies.

**A2. Money is `Decimal`, rounded to 2 places with ROUND_HALF_UP.** It is never a float. Amounts
are displayed as ₹ with Indian digit grouping (₹1,20,000.00).

**A3. "Today" means the processing date in Asia/Kolkata (IST).** Date rules compare against this
date, not the server's UTC date.

**A4. GST model.** Taxes are either CGST + SGST (intra-state) or IGST (inter-state). We record tax
type, rate and amount, and check the arithmetic. We do not check that the rate is correct for
the goods, or that the place of supply matches the tax type. Production would need both checks.

**A5. GSTIN format.** 15 characters: 2 digit state code, 10 character PAN, 1 entity code, `Z`,
1 checksum character. Regex: `^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$`. We do not
validate the checksum character.

**A6. One invoice per PDF, one PO per invoice.** An invoice that references several POs is out of
scope; we use the first PO reference.

**A7. The repo root is `D:\zamp_ai`.** It plays the role of `zamp-ap-agent/` in PLAN.md section 2.

## Ingest and extraction

**A8. Scanned PDF detection.** A PDF is `is_scanned` when pdfplumber finds fewer than 50
characters per page on average. Scanned PDFs skip the grounding check (A13).

**A9. One LLM call per invoice, cached by SHA-256 of the file bytes.** A cache hit (fixture)
counts as a normal extraction. "Force re-extract" bypasses the cache.

**A10. Extraction failure ends the run with status ERROR, not a decision.** If Gemini fails after
retries (rate limit, timeout, invalid JSON), the Extract stage is FAIL with a clear message, the
run is ERROR, and no decision is made. An LLM outage is not a judgement about the invoice.

## Normalize and validate

**A11. Canonical invoice number.** Uppercase, split into alphanumeric runs, strip leading zeros
from each numeric run, join with nothing. `INV/2026/0142` and `INV-2026-142` both become
`INV2026142`. A run that is all zeros becomes `0`.

**A12. Required fields are vendor_name, invoice_number, invoice_date and total.** Missing any one
is a SOFT fail, not HARD, because a person can supply it (EC-3 needs NEEDS_REVIEW). The
confidence check (VAL-CONFIDENCE) applies to these four fields only.

**A13. Grounding compares canonical forms.** Total: every number in the PDF text is parsed to
`Decimal` (commas and ₹ removed), so `1,20,000.00`, `120000` and `₹ 1,20,000` all match 120000.00.
Invoice number: the canonical form (A11) must appear in the canonicalized PDF text. A miss is a
WARN. Skipped (SKIPPED, not PASS) for scanned PDFs.

**A14. Arithmetic.**
- Tax exclusive: sum(line amounts) = subtotal (±₹1), and subtotal + sum(taxes) = total (±₹1).
- Tax inclusive: sum(line amounts) = total (±₹1). Taxes are shown but not added again.
- If a value needed for a check is missing, that check is SKIPPED (the missing field is already
  caught by VAL-REQUIRED).

**A15. Date sanity.** An invoice date after today (A3) is a SOFT fail. An invoice date older than
180 days is a WARN and a review reason (late claims are often legitimate but should be looked at).
A due date before the invoice date is an INFO warning.

## Vendor

**A16. Vendor matching order.** First exact GSTIN match. If none, fuzzy match the extracted name
against legal_name and every alias, using rapidfuzz `token_sort_ratio` after lowercasing,
removing punctuation and removing legal suffixes (pvt, private, ltd, limited, llp, inc, co).
Best score ≥ 90 is a match.

**A17. Name matches but GSTIN differs.** If the vendor was matched by name and the invoice has a
valid GSTIN that differs from the master, that is a WARN and a review reason (VEN-GSTIN). It could
be a second registration, or an impersonation.

**A18. Unknown vendor is SOFT, BLOCKED vendor is HARD.** An unknown vendor may be mid-onboarding,
so a person should look. A BLOCKED vendor must never be paid, so it is REJECTED.

**A19. Bank details.** If the invoice shows a bank account or IFSC and either differs from the
master, that is FRAUD_RISK and NEEDS_REVIEW. The next action tells the reviewer to verify by
calling the phone number on file, never the one on the invoice. If the invoice shows no bank
details, that is fine: we pay to the master account (INFO warning only).

## Purchase orders

**A20. Explicit PO reference.** The PO must exist, belong to the matched vendor, and be OPEN.
Anything else is a SOFT fail (PO-EXPLICIT) and no PO is matched, so the amount check is SKIPPED.
PO numbers are compared after the same canonicalization as invoice numbers (A11).

**A21. PO inference when no reference is given.** Candidates are the vendor's OPEN POs. Each gets
a score from 0 to 1:
- balance fit (weight 0.6): 1.0 if the invoice total is within the tolerance (A23) of the
  remaining balance; otherwise `max(0, 1 - overage / remaining)`.
- description similarity (weight 0.4): for each invoice line, the best rapidfuzz `token_set_ratio`
  against the PO's lines, averaged and divided by 100.

A clear winner has score ≥ 0.75 and leads the second best by ≥ 0.15 (a single candidate only
needs ≥ 0.75). A clear winner is an INFERRED match (WARN, PO_INFERRED, review reason). No clear
winner, or no vendor matched, is a SOFT fail with no PO, and the amount check is SKIPPED.

**A22. Consumed PO balance.** Consumed = sum of totals of runs against this PO with decision
APPROVED, plus NEEDS_REVIEW runs that a reviewer approved. It is always computed, never stored.
Remaining = PO total minus consumed. A reviewer rejection consumes nothing.

**A23. Amount tolerance.** Tolerance = max(2% of remaining balance, ₹500). An invoice total at or
below remaining + tolerance is a PASS. If it is above remaining but within tolerance, the message
says "within tolerance" and gives the amount (HP-2). Above that is a SOFT fail with the exact
overage against remaining, for example "exceeds remaining ₹60,000.00 by ₹30,000.00" (EC-1).

**A24. Unit price variance.** Each invoice line is paired with the PO line whose description is
most similar (≥ 80). If the unit price differs by more than 5%, that is an INFO warning. It is not
a review reason, because the total is already checked by A23. Lines with no pair are listed in
the evidence.

## Duplicates

**A25. Duplicate rules (all HARD, flag DUPLICATE).**
- DUP-HASH: the same file hash was seen in an earlier run.
- DUP-NUMBER: same vendor and same canonical invoice number (A11).
- DUP-FUZZY: same vendor, total within ±₹1, invoice date within 7 days, and canonical invoice
  number similarity (rapidfuzz `ratio`) ≥ 85.

The evidence always links the earlier run. For EC-2, A11 makes the two numbers equal, so DUP-NUMBER
catches it and DUP-FUZZY is a second line of defence.

**A26. Which earlier runs count.** We compare against earlier runs with status DONE, except runs
that were themselves rejected as duplicates (so one duplicate does not create a chain). "Same
vendor" means same matched vendor_id; if no vendor matched, same valid GSTIN; if none, same
normalized vendor name.

**A27. Fuzzy duplicates are rejected, not reviewed.** PLAN.md asks for HARD. The trade-off: a
legitimate second invoice with the same amount within a week and a very similar number would be
rejected. The reviewer can override with a logged note, so this is recoverable.

## Decision and explanation

**A28. Decision order.** Any HARD fail → REJECTED. Otherwise any SOFT fail, or any WARN that is
a review reason → NEEDS_REVIEW. Otherwise APPROVED. Bank mismatch is a SOFT fail, so it always
lands in NEEDS_REVIEW.

**A29. Flags are derived from rules, never set by hand.** The flag column of the severity summary
is the full mapping. A run can carry several flags.

**A30. Human review.** A reviewer can APPROVE or REJECT a NEEDS_REVIEW run, with a note. The
original automated decision is kept; the override is stored next to it with the note and time.
Overriding APPROVED or REJECTED runs is allowed but also logged.

**A31. Explanations are templates.** Each rule outcome maps to a fixed "why" sentence and, where
relevant, a fixed "next action". No LLM is involved, so the explanation cannot contradict the
decision.

## Test data

**A32. Test invoice dates are relative to a fixed anchor date, not today.** The anchor is
`--as-of` in `scripts/generate_invoices.py` (default 2026-11-12). Together with reportlab's
invariant mode and seeded scan noise, this makes the PDFs byte-for-byte identical on every run,
so file hashes and cached Gemini fixtures stay valid. If the demo is close to 180 days after the
anchor, regenerate with a newer `--as-of` and re-record fixtures.

**A33. Test vendors and companies are fictional.** GSTINs follow the format (A5) but are made up.
IFSC prefixes use real bank codes so the bank names look right; branch codes and account numbers
are invented. Emails use the reserved `.example` domain.

**A34. PO total is the cap including GST.** `purchase_orders.csv` `total_amount` is what the
invoice total is compared against (A23). PO line `unit_price` excludes GST. The sum of lines plus
18% GST matches the total to within a paisa or two (PO-2026-0103 is milestone billing whose lines
work out to ₹3,00,000.01 against a cap of ₹3,00,000.00).

**A35. PO lines live in `data/seed/purchase_order_lines.csv`,** one row per line, keyed by
po_number. Nesting lines inside `purchase_orders.csv` would make the CSV awkward to read and edit.

**A36. Unit price comparison on tax-inclusive invoices.** When `tax_inclusive` is true, the invoice
unit price is divided by (1 + GST rate) before comparing with the PO unit price (extends A24).

**A37. Invoice PDFs write "Rs." or "INR", not ₹.** Reportlab's built-in fonts have no ₹ glyph,
and real Indian invoices use both forms, which also exercises extraction. The UI always shows ₹.

**A38. Grand totals are rounded to the nearest rupee with a "Round off" line,** as most Indian
invoices do. The round off is at most ₹0.50, so it stays inside the ±₹1 arithmetic tolerance
(A14).

**A39. Vendor master has extra columns:** `phone` (the "number on file" that EC-4's next action
refers to), `address` and `state` (to choose CGST+SGST or IGST against the buyer's state).

## Pipeline core (Layer 2)

**A40. A rule result can be SKIPPED.** When a check cannot run (scanned PDF for grounding, no PO
for the amount check, no invoice number for duplicate checks) it is stored as SKIPPED with the
reason, so no check is silent. SKIPPED never affects the decision.

**A41. A missing currency is assumed INR.** Every vendor and PO is in INR (A1) and most Indian
invoices print "Rs." rather than a currency code. The Normalize stage records "INR (assumed, not
printed)" so the assumption is visible. A currency that is printed and is not INR still fails
VAL-CURRENCY.

**A42. Flags are truthful even on rejected runs, but next actions follow the decision.** A
duplicate that arrives after the original consumed the PO also fails AMT-REMAINING, so EC-2
carries both `DUPLICATE` and `OVER_PO`: paying it really would overpay the PO. The decision is
still REJECTED, and a rejected run lists next actions only for its HARD reasons ("Do not pay"),
so the reviewer is not told to amend a PO for an invoice that must not be paid.

**A43. Gemini's confidence is self-reported.** The model rates its own confidence, so the numbers
are not calibrated probabilities. They are one signal; the grounding check (A13) is the
independent cross-check on text PDFs. The prompt tells the model to return null rather than guess
for anything not printed, so a missing invoice number surfaces as VAL-REQUIRED, not as a guess.

**A44. IST is a fixed +05:30 offset.** India has no daylight saving, so a fixed offset gives the
same "today" as a time zone database, without adding a dependency on Windows.

**A45. An explicit PO cannot be confirmed without a known vendor.** If the invoice names a real
PO but the vendor did not match, PO-EXPLICIT is a SOFT fail and the amount check is SKIPPED.

**A46. PO inference needs the invoice total.** Without a total the balance fit is 0, so the score
can reach at most 0.40 and no PO is inferred (SOFT fail). The missing total is already
VAL-REQUIRED.
