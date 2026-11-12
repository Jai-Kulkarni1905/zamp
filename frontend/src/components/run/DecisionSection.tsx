import { CircleCheck, History, ListChecks, ListTodo, Scale, UserCheck } from "lucide-react";
import { DECISION_LABELS, formatDateTime, formatMs, formatTime, STAGE_LABELS } from "../../lib/format";
import { styleOf, STATUS_LABELS } from "../../lib/status";
import type { RunDetail, StageEvent } from "../../lib/types";
import { Card, CardHeader, Chip, cx, Label } from "../ui/primitives";
import { RuleList } from "./RuleList";

function DecisionCard({ run }: { run: RunDetail }) {
  const decision = run.decision;
  const s = styleOf(decision ?? "PENDING");
  const Icon = s.icon;
  const exp = run.explanation;
  return (
    <Card className={cx("overflow-hidden", s.border)}>
      <div className={cx("flex flex-col gap-4 px-4 py-4 sm:flex-row sm:items-center", s.row)}>
        <span className={cx("inline-flex items-center gap-2 self-start rounded-control px-3 py-2 text-2xl font-bold", s.solid)}>
          <Icon className="size-6" aria-hidden />
          {DECISION_LABELS[decision ?? ""] ?? "Pending"}
        </span>
        <div className="min-w-0">
          <Label>Verdict</Label>
          <p className="mt-0.5 text-lg font-semibold text-ink">{exp?.verdict}</p>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 px-4 py-4 md:grid-cols-2">
        <div>
          <Label className="mb-2 flex items-center gap-1.5">
            <Scale className="size-3.5" aria-hidden /> Why
          </Label>
          <ul className="space-y-1.5">
            {exp?.why.map((w) => {
              const note = w.startsWith("Note: ");
              return (
                <li key={w} className={cx("flex gap-2 text-sm", note ? "text-ink-3" : "text-ink")}>
                  <span className={cx("mt-1.5 size-1.5 shrink-0 rounded-full", note ? "bg-ink-4" : s.dot)} aria-hidden />
                  {w}
                </li>
              );
            })}
          </ul>
        </div>
        <div>
          <Label className="mb-2 flex items-center gap-1.5">
            <ListTodo className="size-3.5" aria-hidden /> Next action for AP
          </Label>
          <ol className="space-y-1.5">
            {exp?.next_actions.map((a, i) => (
              <li key={a} className="flex gap-2 text-sm text-ink">
                <span className="num grid size-5 shrink-0 place-items-center rounded-chip bg-sunken text-[11px] font-semibold text-ink-2">{i + 1}</span>
                {a}
              </li>
            ))}
          </ol>
        </div>
      </div>
      {run.reviewer_action && (
        <div className={cx("flex items-start gap-2 border-t px-4 py-3 text-sm", styleOf(run.reviewer_action).row, styleOf(run.reviewer_action).border)}>
          <UserCheck className={cx("mt-0.5 size-4 shrink-0", styleOf(run.reviewer_action).text)} aria-hidden />
          <div>
            <span className="font-semibold">{STATUS_LABELS[run.reviewer_action]}</span>
            <span className="text-ink-3"> on {formatDateTime(run.reviewed_at)}</span>
            <p className="mt-0.5 text-ink-2">"{run.reviewer_note}"</p>
          </div>
        </div>
      )}
      <p className="border-t border-line px-4 py-2 text-[11px] text-ink-4">
        Rules-based explanation: built from the rule results by a template. No LLM is involved in deciding or explaining.
      </p>
    </Card>
  );
}

function EventLog({ events }: { events: StageEvent[] }) {
  // RUNNING events drive the live stage cards; the log keeps only the outcome of each stage.
  const finished = events.filter((e) => e.status !== "RUNNING");
  return (
    <Card className="flex min-h-0 flex-col">
      <CardHeader icon={History} title="Event log" subtitle="Each stage outcome, in order (IST)" right={<Chip>{finished.length}</Chip>} />
      <ol className="max-h-[420px] min-h-0 flex-1 space-y-0 overflow-y-auto px-4 py-3">
        {finished.map((e) => {
          const s = styleOf(e.status);
          return (
            <li key={e.seq} className="relative flex gap-3 pb-3 pl-4 before:absolute before:top-2 before:bottom-0 before:left-[3px] before:w-px before:bg-line last:before:hidden">
              <span className={cx("absolute top-1.5 left-0 size-[7px] rounded-full", s.dot)} aria-hidden />
              <div className="min-w-0">
                <div className="num text-[11px] text-ink-3">
                  {formatTime(e.ended_at ?? e.started_at)}
                  {typeof e.payload["duration_ms"] === "number" && <span className="text-ink-4"> · {formatMs(e.payload["duration_ms"])}</span>}
                </div>
                <div className="text-xs font-semibold text-ink">
                  {STAGE_LABELS[e.stage]} <span className={cx("font-medium", s.text)}>{STATUS_LABELS[e.status]}</span>
                </div>
                <div className="text-xs text-ink-3">{e.message}</div>
              </div>
            </li>
          );
        })}
        {finished.length === 0 && <li className="text-xs text-ink-3">Waiting for the first stage to finish.</li>}
      </ol>
    </Card>
  );
}

export function DecisionSection({ run, events }: { run: RunDetail; events: StageEvent[] }) {
  const counted = run.rules.filter((r) => r.outcome !== "SKIPPED");
  const passed = counted.filter((r) => r.outcome === "PASS").length;
  const order = { FAIL: 0, WARN: 1, PASS: 2, SKIPPED: 3 } as const;
  const sorted = [...run.rules].sort((a, b) => order[a.outcome] - order[b.outcome]);
  return (
    <section className="space-y-4" aria-label="Decision">
      {run.decision && <DecisionCard run={run} />}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card className="min-w-0">
          <CardHeader
            icon={ListChecks}
            title="Rule checklist"
            subtitle="Every check, its outcome and evidence"
            right={
              counted.length > 0 && (
                <Chip tone={passed === counted.length ? "PASS" : "WARN"}>
                  <CircleCheck className="mr-1 size-3" aria-hidden />
                  {passed}/{counted.length} passed
                </Chip>
              )
            }
          />
          <div className="max-h-[420px] overflow-y-auto p-3">
            <RuleList rules={sorted} empty="Rules appear as each stage finishes." />
          </div>
        </Card>
        <EventLog events={events} />
      </div>
    </section>
  );
}
