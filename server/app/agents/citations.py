"""Keep only claims the computed facts support.

A claim survives when:

1. it cites at least one fact id, every cited id exists, and
2. every number written in it is found among the values of the facts it cites (allowing
   rounding: 34.6 may be written 35 or 34.6, 0.92 may be written 92).

Anything else is dropped and listed in ``dropped_claims``, so the model cannot add a delay,
a time or a percentage that the analysis did not produce.
"""

from __future__ import annotations

import re
from typing import Any

from app.schemas.analysis import Fact
from app.schemas.llm import Claim

NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def _canon(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def numbers_in(text: str) -> list[str]:
    """Numbers as written (commas dropped, trailing zeros trimmed), in order."""
    found = []
    for match in NUMBER.finditer(text):
        try:
            found.append(_canon(float(match.group().replace(",", ""))))
        except ValueError:
            continue
    return found


def _variants(value: float) -> set[str]:
    out = set()
    for candidate in (value, abs(value), value * 100, abs(value) * 100):
        out.add(_canon(candidate))
        out.add(_canon(round(candidate)))
        out.add(_canon(round(candidate, 1)))
    return out


def allowed_numbers(values: list[Any]) -> set[str]:
    allowed: set[str] = set()
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            allowed |= _variants(float(value))
        elif isinstance(value, str):
            for number in numbers_in(value):
                allowed |= _variants(float(number))
    return allowed


def check_claims(claims: list[Claim], facts: dict[str, Fact]) -> tuple[list[Claim], list[str]]:
    """Split claims into (kept, dropped texts)."""
    kept: list[Claim] = []
    dropped: list[str] = []
    for claim in claims:
        if not claim.fact_ids or any(i not in facts for i in claim.fact_ids):
            dropped.append(claim.text)
            continue
        allowed = allowed_numbers([facts[i].value for i in claim.fact_ids])
        if any(n not in allowed for n in numbers_in(claim.text)):
            dropped.append(claim.text)
            continue
        kept.append(claim)
    return kept, dropped
