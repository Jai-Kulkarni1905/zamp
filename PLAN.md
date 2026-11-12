# PLAN.md: AP Invoice Agent (Zamp ASA Case Study, PS-1)

Build a process that takes a vendor invoice PDF and produces a clear, reasoned decision
(APPROVED / NEEDS_REVIEW / REJECTED), with every stage visible live and a dashboard of all runs.

## 0. Core design principle

**The LLM extracts. Rules decide. Templates explain.**

- Gemini is used for exactly one job: reading a messy PDF (text or scanned) into a strict JSON schema, with a confidence score per field.
- Every decision is made by a deterministic rules engine in Python. Same input, same decision, every time. Every rule result is stored and shown.
- The explanation is built from rule results by a template, so it can never contradict the decision.
- Why: auditability, reproducibility, and it keeps us inside the Gemini free tier (1 LLM call per invoice).

## 1. Stack

| Part | Choice |
|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 |
| DB | SQLite locally; Postgres in prod via `DATABASE_URL` (same code) |
| LLM | Gemini via `google-genai` SDK, native PDF input, `response_schema` structured output. Model name from env `GEMINI_MODEL` |
| PDF utils | `pdfplumber` (text layer detection + grounding check), `PyMuPDF` (render for preview + make scanned test files) |
| Fuzzy matching | `rapidfuzz` |
| Live updates | Server-Sent Events (SSE) |
| Frontend | React + Vite + TypeScript + Tailwind, React Router, native `EventSource` |
| Test data | `reportlab` (invoice PDFs), Pillow (scan noise) |
| Deploy | One Docker container: FastAPI serves the built React app. Host + DB decided in Layer 7 |

## 2. Folder structure

```
zamp-ap-agent/
  CLAUDE.md
  PLAN.md
  .env.example            # GEMINI_API_KEY, GEMINI_MODEL, DATABASE_URL, LLM_MODE
  docs/
    process-map.md        # stage by stage map (Layer 0)
    assumptions.md        # every assumption, referenced in the interview
    demo-script.md        # exact run order for video + live demo (Layer 7)
  data/
    seed/vendors.csv
    seed/purchase_orders.csv
    invoices/             # generated test PDFs
    fixtures/             # recorded Gemini extraction JSON, keyed by file hash
  scripts/
    generate_invoices.py
    seed_db.py
  backend/
    app/
      main.py  config.py  db.py  models.py  schemas.py
      llm/gemini.py       # the ONLY file that talks to Gemini
      pipeline/
        runner.py         # orchestrates stages, emits events
        events.py         # event bus (in-memory queue + DB persistence)
        stages/ingest.py extract.py normalize.py validate.py
               vendor.py po_match.py duplicates.py decide.py explain.py
      routes/runs.py pos.py vendors.py stats.py admin.py
    tests/
  frontend/
  Dockerfile
```

## 3. Domain model

**Vendor master** (`vendors.csv`): vendor_id, legal_name, aliases, gstin, status (APPROVED / BLOCKED), bank_account, ifsc, email.

**Purchase orders** (`purchase_orders.csv`): po_number, vendor_id, issue_date, currency, total_amount, line items (description, qty, unit_price), status (OPEN / CLOSED). Consumed balance is computed from approved invoices, never stored by hand.

**Run**: id, file_hash, filename, status (QUEUED / RUNNING / DONE / ERROR), decision, flags, extracted_json, normalized_json, matched_po, created_at, duration_ms, reviewer_action, reviewer_note.

**StageEvent**: run_id, stage, status (RUNNING / PASS / WARN / FAIL / SKIPPED), started_at, ended_at, payload_json, message.

**RuleResult**: run_id, rule_id, outcome (PASS / WARN / FAIL), severity (INFO / SOFT / HARD), message, evidence_json.

## 4. Pipeline stages

Each stage writes a StageEvent and pushes it to the SSE stream.

1. **Ingest**: save file, SHA-256 hash, page count, detect text layer (`is_scanned` = almost no extractable chars). Exact same file hash seen before = instant duplicate signal.
2. **Extract (Gemini)**: send PDF bytes + schema. Schema fields: vendor_name, vendor_gstin, invoice_number, invoice_date, due_date, po_reference (null if absent), currency, line_items[description, qty, unit_price, amount], subtotal, taxes[type, rate, amount], tax_inclusive, total, bank_account, ifsc. Each field also returns `confidence` (0 to 1) and `source_text` (the snippet it read). Results cached by file hash in `data/fixtures/`.
3. **Normalize**: dates to ISO, money to `Decimal`, canonical invoice number (uppercase, strip non-alphanumerics, strip leading zeros in numeric runs), GSTIN format check.
4. **Validate (data quality)**:
   - required fields present (invoice_number, date, total, vendor)
   - arithmetic: sum(line items) = subtotal (±₹1), subtotal + tax = total (±₹1), handle tax-inclusive
   - grounding: if text layer exists, extracted total and invoice number must literally appear in the PDF text, else confidence downgraded
   - date sanity: not in the future, not older than 180 days
   - any required field with confidence < 0.7 = WARN
5. **Vendor check**: match by GSTIN exact, else fuzzy legal_name / aliases (≥ 90). Vendor must be APPROVED. Bank account + IFSC on invoice must equal vendor master.
6. **PO match**:
   - explicit `po_reference` → direct lookup, must belong to same vendor
   - missing → infer: open POs of this vendor, score by remaining balance vs invoice total and line item description similarity. One clear winner = INFERRED match (WARN). Zero or several close = no match (FAIL soft)
7. **Amount check**: compare invoice total against PO **remaining** balance (PO total minus already approved invoices). Tolerance: within max(2%, ₹500) = PASS; above = FAIL soft with exact overage. Line level: unit price variance > 5% vs PO = WARN.
8. **Duplicate check**: (a) same file hash, (b) same vendor + same canonical invoice number, (c) fuzzy: same vendor + total within ₹1 + date within 7 days + invoice number similarity ≥ 85. (a) or (b) = FAIL hard. (c) = FAIL hard with link to the original run.
9. **Decide**:
   - any HARD fail → REJECTED
   - any SOFT fail, or any WARN marked review-worthy, or bank mismatch → NEEDS_REVIEW
   - else → APPROVED (approved amount is deducted from PO balance)
   - flags: `FRAUD_RISK`, `PO_INFERRED`, `LOW_CONFIDENCE`, `OVER_PO`, `DUPLICATE`
10. **Explain**: template turns rule results into (a) a one-line verdict, (b) "why" bullets, (c) "next action" for the AP person (e.g. "Ask vendor for invoice number", "Verify bank change by calling the number on file, not the one on the invoice"). No LLM call here.

## 5. API

```
POST /api/runs                  multipart file → {run_id}   (pipeline starts as background task)
GET  /api/runs/{id}/events      SSE: replays stored events, then streams live ones
GET  /api/runs                  list, filters: decision, vendor, date
GET  /api/runs/{id}             full detail (stages, rules, extraction, decision)
GET  /api/runs/{id}/file        original PDF for preview
POST /api/runs/{id}/review      {action: APPROVE|REJECT, note}  human override, logged
GET  /api/pos                   POs with consumed / remaining balance
GET  /api/vendors
GET  /api/stats                 KPIs for dashboard
POST /api/admin/reset           wipe runs, reseed (for demo prep)
```

## 6. UI

**Live run view** (`/run/:id`)
- Left: PDF preview. Right: vertical stage timeline, each stage pending → running (spinner) → PASS/WARN/FAIL with duration.
- Expandable per stage: extracted fields table with confidence bars (low confidence highlighted), rule checklist with evidence, PO match card showing PO total / consumed / remaining / this invoice.
- Bottom: decision card (big status, verdict line, why bullets, next action). For NEEDS_REVIEW: Approve / Reject buttons with note.

**Dashboard** (`/`)
- KPI strip: runs, approval rate, review queue count, avg processing time, ₹ value processed.
- Upload dropzone (drag a PDF → navigates to live run view).
- Runs table: time, vendor, invoice no., amount, PO, decision badge, flags. Filters + search.
- Tabs: All runs / Review queue / Purchase orders (balances, so split-PO is visible).

Design bar: clean, calm, finance-tool feel. Status colors consistent everywhere (green / amber / red). Every number formatted in ₹ with Indian grouping.

## 7. Test inputs and expected outcomes

| ID | Scenario | Expected |
|---|---|---|
| HP-1 | Clean PDF, explicit PO, exact match | APPROVED |
| HP-2 | Different layout, tax-inclusive pricing, total 1.5% above PO | APPROVED, note "within tolerance" |
| EC-1 | **Split PO**: PO ₹3,00,000. Invoice A ₹1,20,000, B ₹1,20,000 (both approve), C ₹90,000 | C → NEEDS_REVIEW, `OVER_PO`, "exceeds remaining ₹60,000 by ₹30,000" |
| EC-2 | **Disguised duplicate**: HP-1 re-sent with new layout, number `INV/2026/0142` vs original `INV-2026-142`, different file hash | REJECTED, `DUPLICATE`, links original run |
| EC-3 | **Scanned + missing data**: image-only PDF, no invoice number, no PO reference | NEEDS_REVIEW, `LOW_CONFIDENCE`, `PO_INFERRED`, next action lists exactly what's missing |
| EC-4 | **Bank details changed**: approved vendor, valid PO, bank account differs from master | NEEDS_REVIEW, `FRAUD_RISK`, "verify by phone on file" |

Run order matters for EC-1 and EC-2 (they depend on earlier approved runs). This order goes in `docs/demo-script.md`.

## 8. Gemini free tier protection

- 1 call per invoice. Explain stage is template, not LLM.
- Extraction cached by file hash. UI has a "force re-extract" toggle for when you want to show a live call.
- `LLM_MODE=live|fixture`. Tests and dev loops use `fixture` (recorded JSON). Only switch to `live` deliberately.
- Retry with backoff on 429. If quota is exhausted, the Extract stage shows a clear "LLM rate limited, retry" state, never a crash.
- Check the current free models and your quota in Google AI Studio; set `GEMINI_MODEL` accordingly. Prefer a Flash model.
- Talking point: free tier data may be used by Google, fine for synthetic data; production would use a paid / enterprise tier.

## 9. Build layers

Do ONE layer per Claude Code session. Each layer ends with its acceptance check passing and a git commit.

### Layer 0: Process map + assumptions
- Write `docs/process-map.md` (stages, inputs, outputs, decision points) and `docs/assumptions.md` (tolerances, currency INR, GST, 180 day rule, thresholds).
- **Done when:** Soumil has read both and agrees with every threshold.

### Layer 1: Test data
- `vendors.csv` (5 to 6 vendors, one BLOCKED), `purchase_orders.csv` (6 to 8 POs, including the ₹3,00,000 split PO).
- `scripts/generate_invoices.py`: at least 3 visually distinct invoice templates; outputs every file in section 7; EC-3 rendered to image, rotated 1 to 2°, noise added, saved as image-only PDF.
- **Done when:** all PDFs open and look like real invoices from different companies.

### Layer 2: Pipeline core (no UI)
- Models, DB, all stages, rules engine, `llm/gemini.py` with fixture mode.
- CLI: `python -m app.cli run data/invoices/HP-1.pdf` prints stage results + decision JSON.
- Record real Gemini fixtures for all test PDFs once (ask Soumil before doing this).
- Unit tests for normalize, duplicates, po_match, decide using fixtures.
- **Done when:** HP-1 and HP-2 give the expected decision via CLI, tests pass.

### Layer 3: API + persistence + events
- All endpoints in section 5, background task runner, SSE with replay.
- **Done when:** uploading via curl and `curl -N` on the events endpoint shows stages streaming.

### Layer 4: Live run view
- Vite app, upload, `/run/:id` page per section 6.
- **Done when:** dragging HP-1 into the browser shows each stage light up and the decision card.

### Layer 5: Dashboard
- KPIs, runs table, filters, review queue, PO balances tab, human review actions.
- **Done when:** after running all test files, dashboard numbers and PO balances are correct.

### Layer 6: Edge cases
- Implement and verify EC-1 → EC-4 one at a time, in that order. Each gets a test.
- **Done when:** full section 7 table reproduces exactly, from a fresh reset, in demo order.

### Layer 7: Deploy + demo prep
- Dockerfile, deploy, prod DB, reset endpoint, `docs/demo-script.md`.
- Rehearse: reset → run all 6 in order, twice, zero errors.
- **Done when:** live URL works from a phone on mobile data.

## 10. Suggested week

| Day | Work |
|---|---|
| 1 | Email PS-1 choice to coordinator. Layer 0 + Layer 1 |
| 2 | Layer 2 |
| 3 | Layer 3 + Layer 4 |
| 4 | Layer 5 |
| 5 | Layer 6 |
| 6 | Layer 7, rehearse |
| 7 | Record 5 min video, submit link + video |

## 11. Status (Claude Code updates this after each layer)

- [x] Layer 0
- [x] Layer 1
- [x] Layer 2
- [x] Layer 3
- [x] Layer 4
- [x] Layer 5
- [ ] Layer 6
- [ ] Layer 7
