"""The eval harness passes on the samples: every planted pattern is found."""

from __future__ import annotations

from app.container import Container
from app.services.evaluate import evaluate


async def test_every_eval_check_passes(
    seeded: Container, truth: dict, chat_cases: list[dict]
) -> None:
    sections = await evaluate(seeded, truth, chat_cases)
    failed = [
        f"{s.name}: {c['check']} ({c['detail']})"
        for s in sections
        for c in s.checks
        if not c["passed"]
    ]
    assert not failed, failed
    assert {s.name for s in sections} == {"analysis", "forecast", "live", "chat"}
    assert sum(len(s.checks) for s in sections) >= 15
