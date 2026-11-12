"""Stage 9: deterministic decision from rule results (A28, A29). No LLM."""

from __future__ import annotations

from app.schemas import (
    Decision,
    DecisionResult,
    Flag,
    Outcome,
    RuleResult,
    Severity,
    Stage,
    StageResult,
    StageStatus,
)

_STATUS = {Decision.APPROVED: StageStatus.PASS, Decision.NEEDS_REVIEW: StageStatus.WARN,
           Decision.REJECTED: StageStatus.FAIL}


def decide(rules: list[RuleResult]) -> tuple[StageResult, DecisionResult]:
    hard = [r.rule_id for r in rules if r.outcome == Outcome.FAIL and r.severity == Severity.HARD]
    soft = [r.rule_id for r in rules if r.outcome == Outcome.FAIL and r.severity != Severity.HARD]
    review = [r.rule_id for r in rules if r.outcome == Outcome.WARN and r.review_reason]

    if hard:
        decision = Decision.REJECTED
    elif soft or review:
        decision = Decision.NEEDS_REVIEW
    else:
        decision = Decision.APPROVED

    raised = {r.flag for r in rules if r.flag is not None and r.outcome in (Outcome.WARN, Outcome.FAIL)}
    flags = [f for f in Flag if f in raised]
    result = DecisionResult(decision=decision, flags=flags, hard_fails=hard, soft_fails=soft, review_warnings=review)
    message = decision.value + (f" ({', '.join(flags)})" if flags else "")
    stage = StageResult(stage=Stage.DECIDE, message=message, payload=result.model_dump(mode="json"),
                        status_override=_STATUS[decision])
    return stage, result
