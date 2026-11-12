"""Money and identifier helpers. Money is always Decimal (A2)."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

TWO = Decimal("0.01")
ZERO = Decimal("0.00")

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_CURRENCY_TOKENS = re.compile(r"(?i)rs\.?|inr|₹|rupees")
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")  # A5


def q2(value: Decimal) -> Decimal:
    return value.quantize(TWO, rounding=ROUND_HALF_UP)


def parse_amount(text: str | int | float | Decimal | None) -> Decimal | None:
    """'Rs. 1,77,000.00' / 'INR 90,000' / '(500)' / '-0.01' -> Decimal, or None if no number."""
    if text is None:
        return None
    if isinstance(text, Decimal):
        return q2(text)
    if isinstance(text, (int, float)):
        return q2(Decimal(str(text)))
    s = _CURRENCY_TOKENS.sub("", text).replace(" ", "").strip()
    negative = (s.startswith("(") and s.endswith(")")) or s.startswith("-")
    m = _NUMBER.search(s)
    if not m:
        return None
    try:
        value = Decimal(m.group().replace(",", ""))
    except InvalidOperation:
        return None
    return q2(-value if negative else value)


def numbers_in_text(text: str) -> set[Decimal]:
    """Every number in a block of text, parsed to Decimal (used for grounding, A13)."""
    found: set[Decimal] = set()
    for m in _NUMBER.finditer(text):
        try:
            found.add(q2(Decimal(m.group().replace(",", ""))))
        except InvalidOperation:
            continue
    return found


def canonical_ref(value: str | None) -> str | None:
    """Canonical invoice / PO number (A11): INV/2026/0142 and INV-2026-142 -> INV2026142."""
    if not value:
        return None
    runs = re.findall(r"[A-Z]+|\d+", value.upper())
    if not runs:
        return None
    return "".join(r.lstrip("0") or "0" if r.isdigit() else r for r in runs)


def is_valid_gstin(gstin: str | None) -> bool:
    return bool(gstin) and bool(GSTIN_RE.match(gstin or ""))


def inr(value: Decimal | None, symbol: bool = True) -> str:
    """Indian digit grouping: Decimal('177000') -> '₹1,77,000.00'."""
    if value is None:
        return "n/a"
    value = q2(value)
    sign = "-" if value < 0 else ""
    whole, frac = f"{abs(value):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"{sign}{'₹' if symbol else ''}{whole}.{frac}"


def mask_account(account: str | None) -> str | None:
    """Show only the last 4 digits of a bank account."""
    if not account:
        return None
    return "XXXX" + account[-4:]
