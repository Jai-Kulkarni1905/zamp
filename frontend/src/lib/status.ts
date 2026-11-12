// The one status color map (docs/design-system.md). Components never choose status colors themselves.

import {
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleMinus,
  CircleX,
  LoaderCircle,
  type LucideIcon,
} from "lucide-react";

export type Tone = "approve" | "review" | "reject" | "running" | "neutral";

export interface ToneStyle {
  /** Pill / badge: tinted bg, dark text, light border. */
  pill: string;
  /** Whole-row highlight. */
  row: string;
  /** Solid fill for primary buttons and the decision badge. */
  solid: string;
  /** Text color for inline values. */
  text: string;
  /** Border color for accented cards. */
  border: string;
  /** Small dot / bar fill. */
  dot: string;
  icon: LucideIcon;
}

const TONES: Record<Tone, ToneStyle> = {
  approve: {
    pill: "bg-approve-50 text-approve-800 border-approve-300",
    row: "bg-approve-50",
    solid: "bg-approve-700 text-white",
    text: "text-approve-700",
    border: "border-approve-300",
    dot: "bg-approve-600",
    icon: CircleCheck,
  },
  review: {
    pill: "bg-review-50 text-review-800 border-review-300",
    row: "bg-review-50",
    solid: "bg-review-600 text-white",
    text: "text-review-700",
    border: "border-review-300",
    dot: "bg-review-600",
    icon: CircleAlert,
  },
  reject: {
    pill: "bg-reject-50 text-reject-700 border-reject-300",
    row: "bg-reject-50",
    solid: "bg-reject-600 text-white",
    text: "text-reject-700",
    border: "border-reject-300",
    dot: "bg-reject-600",
    icon: CircleX,
  },
  running: {
    pill: "bg-accent-50 text-accent-700 border-accent-200",
    row: "bg-accent-50",
    solid: "bg-accent-600 text-white",
    text: "text-accent-700",
    border: "border-accent-200",
    dot: "bg-accent-600",
    icon: LoaderCircle,
  },
  neutral: {
    pill: "bg-sunken text-ink-3 border-line",
    row: "",
    solid: "bg-ink-3 text-white",
    text: "text-ink-3",
    border: "border-line",
    dot: "bg-ink-4",
    icon: CircleDashed,
  },
};

const STATUS_TONE: Record<string, Tone> = {
  APPROVED: "approve",
  APPROVE: "approve",
  PASS: "approve",
  DONE: "approve",
  NEEDS_REVIEW: "review",
  WARN: "review",
  REJECTED: "reject",
  REJECT: "reject",
  FAIL: "reject",
  ERROR: "reject",
  RUNNING: "running",
  QUEUED: "neutral",
  PENDING: "neutral",
  SKIPPED: "neutral",
};

export function toneOf(status: string | null | undefined): Tone {
  return (status && STATUS_TONE[status]) || "neutral";
}

export function styleOf(status: string | null | undefined): ToneStyle {
  const tone = toneOf(status);
  const base = TONES[tone];
  if (status === "SKIPPED") return { ...base, icon: CircleMinus };
  return base;
}

export const STATUS_LABELS: Record<string, string> = {
  APPROVED: "Approved",
  NEEDS_REVIEW: "Needs review",
  REJECTED: "Rejected",
  PASS: "Pass",
  WARN: "Warn",
  FAIL: "Fail",
  SKIPPED: "Skipped",
  PENDING: "Pending",
  RUNNING: "Running",
  QUEUED: "Queued",
  DONE: "Done",
  ERROR: "Error",
  APPROVE: "Approved by reviewer",
  REJECT: "Rejected by reviewer",
};
