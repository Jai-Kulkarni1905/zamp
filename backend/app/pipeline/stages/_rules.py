"""Small constructor so every rule result is built the same way."""

from __future__ import annotations

from typing import Any

from app.schemas import Flag, Outcome, RuleResult, Severity, Stage

FIELD_LABELS = {
    "vendor_name": "vendor name",
    "invoice_number": "invoice number",
    "invoice_date": "invoice date",
    "total": "invoice total",
}


def rule(
    stage: Stage,
    rule_id: str,
    outcome: Outcome,
    severity: Severity,
    message: str,
    evidence: dict[str, Any] | None = None,
    *,
    review: bool = False,
    flag: Flag | None = None,
) -> RuleResult:
    """Build a RuleResult. `review` and `flag` only take effect when the rule WARNs or FAILs."""
    triggered = outcome in (Outcome.WARN, Outcome.FAIL)
    return RuleResult(
        rule_id=rule_id,
        stage=stage,
        outcome=outcome,
        severity=severity,
        message=message,
        evidence=evidence or {},
        review_reason=review and triggered,
        flag=flag if triggered else None,
    )


def skipped(stage: Stage, rule_id: str, reason: str) -> RuleResult:
    return rule(stage, rule_id, Outcome.SKIPPED, Severity.INFO, reason)
