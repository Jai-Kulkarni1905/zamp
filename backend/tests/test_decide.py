from app.pipeline.stages._rules import rule
from app.pipeline.stages.decide import decide
from app.schemas import Decision, Flag, Outcome, Severity, Stage, StageStatus

S = Stage.VALIDATE


def ok(rule_id: str = "X") -> object:
    return rule(S, rule_id, Outcome.PASS, Severity.SOFT, "ok", review=True)


def test_all_pass_is_approved() -> None:
    stage, d = decide([ok("A"), ok("B")])  # type: ignore[list-item]
    assert d.decision == Decision.APPROVED and d.flags == [] and stage.status == StageStatus.PASS


def test_hard_fail_rejects_even_with_soft() -> None:
    rules = [rule(S, "VEN-BANK", Outcome.FAIL, Severity.SOFT, "x", review=True, flag=Flag.FRAUD_RISK),
             rule(S, "DUP-NUMBER", Outcome.FAIL, Severity.HARD, "x", flag=Flag.DUPLICATE)]
    stage, d = decide(rules)
    assert d.decision == Decision.REJECTED and stage.status == StageStatus.FAIL
    assert d.flags == [Flag.FRAUD_RISK, Flag.DUPLICATE]
    assert d.hard_fails == ["DUP-NUMBER"]


def test_soft_fail_needs_review() -> None:
    _, d = decide([rule(S, "AMT-REMAINING", Outcome.FAIL, Severity.SOFT, "x", review=True, flag=Flag.OVER_PO)])
    assert d.decision == Decision.NEEDS_REVIEW and d.flags == [Flag.OVER_PO]


def test_review_warning_needs_review() -> None:
    _, d = decide([rule(S, "PO-INFER", Outcome.WARN, Severity.SOFT, "x", review=True, flag=Flag.PO_INFERRED)])
    assert d.decision == Decision.NEEDS_REVIEW and d.review_warnings == ["PO-INFER"]


def test_info_warning_does_not_block_approval() -> None:
    _, d = decide([rule(S, "AMT-UNIT-PRICE", Outcome.WARN, Severity.INFO, "x"),
                   rule(S, "VEN-BANK-MISSING", Outcome.WARN, Severity.INFO, "x")])
    assert d.decision == Decision.APPROVED


def test_skipped_rules_are_ignored() -> None:
    _, d = decide([rule(S, "VAL-GROUNDING", Outcome.SKIPPED, Severity.INFO, "scanned")])
    assert d.decision == Decision.APPROVED


def test_flags_not_raised_on_pass() -> None:
    _, d = decide([rule(S, "VEN-BANK", Outcome.PASS, Severity.SOFT, "x", review=True, flag=Flag.FRAUD_RISK)])
    assert d.flags == []


def test_duplicate_drops_over_po_flag_but_keeps_the_rule() -> None:
    over = rule(S, "AMT-REMAINING", Outcome.FAIL, Severity.SOFT, "over", review=True, flag=Flag.OVER_PO)
    dup = rule(S, "DUP-NUMBER", Outcome.FAIL, Severity.HARD, "dup", flag=Flag.DUPLICATE)
    stage, d = decide([over, dup])
    assert d.decision == Decision.REJECTED and d.flags == [Flag.DUPLICATE]
    assert "AMT-REMAINING" in d.soft_fails  # still counted and shown, just not flagged


def test_over_po_kept_when_not_a_duplicate() -> None:
    fraud = rule(S, "VEN-BANK", Outcome.FAIL, Severity.SOFT, "x", review=True, flag=Flag.FRAUD_RISK)
    over = rule(S, "AMT-REMAINING", Outcome.FAIL, Severity.SOFT, "x", review=True, flag=Flag.OVER_PO)
    _, d = decide([fraud, over])
    assert d.flags == [Flag.FRAUD_RISK, Flag.OVER_PO]
