// Mirrors backend/app/api_schemas.py. Money and quantities arrive as strings (Decimal), never floats.

export type Money = string;

export type Decision = "APPROVED" | "NEEDS_REVIEW" | "REJECTED";
export type RunStatus = "QUEUED" | "RUNNING" | "DONE" | "ERROR";
export type StageStatus = "PENDING" | "RUNNING" | "PASS" | "WARN" | "FAIL" | "SKIPPED";
export type Outcome = "PASS" | "WARN" | "FAIL" | "SKIPPED";
export type Severity = "INFO" | "SOFT" | "HARD";
export type Flag = "FRAUD_RISK" | "PO_INFERRED" | "LOW_CONFIDENCE" | "OVER_PO" | "DUPLICATE";

export const STAGES = [
  "ingest",
  "extract",
  "normalize",
  "validate",
  "vendor",
  "po_match",
  "amount",
  "duplicates",
  "decide",
  "explain",
] as const;
export type StageName = (typeof STAGES)[number];

export type Payload = Record<string, unknown>;

export interface StageView {
  stage: StageName;
  status: StageStatus;
  message: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  payload: Payload;
}

export interface RuleView {
  stage: StageName;
  rule_id: string;
  outcome: Outcome;
  severity: Severity;
  review_reason: boolean;
  flag: Flag | null;
  message: string;
  evidence: Payload;
}

export interface POBalance {
  po_number: string;
  vendor_id: string;
  vendor_name: string | null;
  status: string;
  issue_date: string;
  total: Money;
  consumed: Money;
  remaining: Money;
}

export interface Explanation {
  verdict: string;
  why: string[];
  next_actions: string[];
}

export interface RunSummary {
  id: string;
  filename: string;
  status: RunStatus;
  decision: Decision | null;
  effective_decision: Decision | null;
  flags: Flag[];
  vendor_id: string | null;
  vendor_name: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  total: Money | null;
  matched_po: string | null;
  po_match_type: "EXPLICIT" | "INFERRED" | null;
  created_at: string;
  duration_ms: number | null;
  reviewer_action: "APPROVE" | "REJECT" | null;
}

export interface RunDetail extends RunSummary {
  file_hash: string;
  error: string | null;
  reviewer_note: string | null;
  reviewed_at: string | null;
  explanation: Explanation | null;
  extracted: Payload | null;
  normalized: Payload | null;
  stages: StageView[];
  rules: RuleView[];
  po: POBalance | null;
  file_url: string;
  events_url: string;
}

export interface StageEvent {
  run_id: string;
  seq: number;
  stage: StageName;
  status: Exclude<StageStatus, "PENDING">;
  message: string;
  started_at: string;
  ended_at: string | null;
  payload: Payload;
}

export interface EndEvent {
  run_id: string;
  status: RunStatus | null;
  decision: Decision | null;
  flags: Flag[];
}

export interface RunCreated {
  run_id: string;
  status: RunStatus;
  events_url: string;
  detail_url: string;
}

export interface Health {
  ok: boolean;
  llm_mode: "fixture" | "live";
  worker_busy: boolean;
}

// Stage payload shapes used by the detail panels (see backend/app/pipeline/stages/*).

export interface ExtractedFieldRow {
  field: string;
  value: string | boolean | null;
  confidence: number;
  source_text: string | null;
  required: boolean;
  low_confidence: boolean;
}

export interface POCard {
  po_number: string;
  vendor_id: string;
  status: string;
  match_type: "EXPLICIT" | "INFERRED" | null;
  total: Money;
  consumed: Money;
  remaining: Money;
  invoice_total: Money | null;
  remaining_after: Money | null;
}

export interface POCandidate {
  po_number: string;
  score: number;
  balance_fit: number;
  description_similarity: number;
  remaining: Money;
}

export interface UnitPriceRow {
  description: string;
  paired: string | null;
  po_line_no?: number;
  invoice_unit_price?: Money;
  po_unit_price?: Money;
  variance_pct?: number;
  flagged?: boolean;
  similarity?: number;
}
