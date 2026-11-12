import { ChevronDown, Workflow } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { formatMs, STAGE_HINTS, STAGE_LABELS } from "../../lib/format";
import { styleOf } from "../../lib/status";
import type { RuleView, StageName, StageView } from "../../lib/types";
import { Card, CardHeader, cx, ProgressBar, StatusPill } from "../ui/primitives";
import { StageDetail } from "./StageDetails";

function StageCard({
  index,
  stage,
  rules,
  open,
  onToggle,
}: {
  index: number;
  stage: StageView;
  rules: RuleView[];
  open: boolean;
  onToggle: () => void;
}) {
  const flagged = stage.status === "WARN" || stage.status === "FAIL";
  const s = styleOf(stage.status);
  const pending = stage.status === "PENDING";
  return (
    <li className={cx("border-b border-line last:border-b-0", flagged && s.row, stage.status === "RUNNING" && "bg-accent-50/60")}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-start gap-3 px-4 py-3 text-left focus-visible:shadow-focus focus-visible:outline-none"
      >
        <span
          className={cx(
            "num mt-0.5 grid size-6 shrink-0 place-items-center rounded-chip border text-[11px] font-semibold",
            pending ? "border-line bg-sunken text-ink-4" : s.pill,
          )}
        >
          {String(index + 1).padStart(2, "0")}
        </span>
        <span className="min-w-0 flex-1">
          <span className={cx("block text-base font-semibold", pending ? "text-ink-3" : "text-ink")}>{STAGE_LABELS[stage.stage]}</span>
          <span className={cx("block text-xs", pending ? "text-ink-4" : "text-ink-3")}>
            {stage.message && !pending && stage.status !== "RUNNING" ? stage.message : STAGE_HINTS[stage.stage]}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {stage.duration_ms !== null && !pending && <span className="num hidden text-xs text-ink-4 sm:inline">{formatMs(stage.duration_ms)}</span>}
          <StatusPill status={stage.status} />
          <ChevronDown className={cx("size-4 text-ink-4 transition-transform", open && "rotate-180")} aria-hidden />
        </span>
      </button>
      {open && (
        <div className="px-4 pb-4 sm:pl-13">
          <StageDetail stage={stage} rules={rules} />
        </div>
      )}
    </li>
  );
}

export function StageTimeline({ stages, rules, live }: { stages: StageView[]; rules: RuleView[]; live: boolean }) {
  const [open, setOpen] = useState<Set<StageName>>(new Set());
  const touched = useRef<Set<StageName>>(new Set());

  // Auto-open stages that warn or fail, unless the user already toggled them.
  useEffect(() => {
    setOpen((prev) => {
      const next = new Set(prev);
      for (const s of stages) {
        if ((s.status === "WARN" || s.status === "FAIL") && !touched.current.has(s.stage)) next.add(s.stage);
      }
      return next.size === prev.size ? prev : next;
    });
  }, [stages]);

  const toggle = (name: StageName) => {
    touched.current.add(name);
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const finished = stages.filter((s) => s.status !== "PENDING" && s.status !== "RUNNING").length;
  const counts = {
    pass: stages.filter((s) => s.status === "PASS").length,
    warn: stages.filter((s) => s.status === "WARN").length,
    fail: stages.filter((s) => s.status === "FAIL").length,
  };

  return (
    <Card>
      <CardHeader
        icon={Workflow}
        title="Pipeline stages"
        subtitle="The LLM extracts. Rules decide. Templates explain."
        right={
          <span className="num shrink-0 text-xs text-ink-3">
            {finished}/10{counts.warn ? ` · ${counts.warn} warn` : ""}
            {counts.fail ? ` · ${counts.fail} fail` : ""}
          </span>
        }
      />
      {live && (
        <div className="px-4 pt-3">
          <ProgressBar value={finished / 10} label="Stages finished" />
        </div>
      )}
      <ol>
        {stages.map((s, i) => (
          <StageCard
            key={s.stage}
            index={i}
            stage={s}
            rules={rules.filter((r) => r.stage === s.stage)}
            open={open.has(s.stage)}
            onToggle={() => toggle(s.stage)}
          />
        ))}
      </ol>
    </Card>
  );
}
