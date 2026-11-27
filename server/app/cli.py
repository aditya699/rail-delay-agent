"""Command line: the whole pipeline without the web app.

    uv run python -m app.cli --fake demo        # seed, ingest, train, print patterns, sample chats
    uv run python -m app.cli --fake eval        # score everything against samples/ground_truth.json
    uv run python -m app.cli --fake ask "22448 ka status kya hai?"
    uv run python -m app.cli train              # rebuild the analytics, print the model card
    uv run python -m app.cli ingest             # poll the live source once into the database
    uv run python -m app.cli ingest --watch     # keep polling (run the poller as its own process)
    uv run python -m app.cli ingest --history my_runs.csv   # import running history

``demo`` and ``eval`` work in a temporary database; the others use the server's database
(``server/.env``). ``--fake`` forces demo mode without an API key.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app.agents.chat import ChatResult
from app.analysis.stations import MONTHS, month_label
from app.container import Container, build_container
from app.core.config import Settings
from app.core.logging import configure_logging
from app.services.demo import seed_demo
from app.services.evaluate import evaluate


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def print_patterns(container: Container) -> None:
    analytics = container.analytics.current
    stations = analytics.stations
    print(
        f"\nHistory: {len(analytics.stops):,} stop rows up to {analytics.as_of}, "
        f"built in {analytics.seconds}s"
    )
    print("\nWhere trains ADD delay (mean minutes gained approaching the station, 95% CI by day):")
    for s in stations.stations[:6]:
        print(
            f"  #{s.rank} {s.code:<5} {s.name:<28} added {s.added_mean:5.1f} "
            f"[{s.added_ci_low:4.1f}-{s.added_ci_high:4.1f}]  inherited {s.inherited_mean:5.1f}"
        )
    naive = next(s for s in stations.stations if s.code == stations.naive_top)
    print(
        f"  Worst ARRIVAL delay is {naive.code} ({naive.arrival_mean:.0f} min), but it adds only "
        f"{naive.added_mean:.0f}: the rest is inherited."
    )
    for months in ([12, 1], [7, 8]):
        top = container.analytics.hotspots(months).stations[:3]
        print(
            f"  {month_label(months)}: "
            + ", ".join(f"{s.code} {s.added_mean:.0f} min" for s in top)
        )
    print("\nSeasonal months (added delay well above the station's typical month):")
    for item in analytics.seasonality.seasonal:
        if item.months:
            print(
                f"  {item.station:<5} {month_label(item.months):<10} "
                f"peak {MONTHS[item.peak_month - 1]} {item.peak_added:.0f} min"
            )
    for window in analytics.seasonality.windows:
        print(
            f"  Hour window: {window.station} {window.label}, "
            f"+{window.excess:.0f} min (seasons excluded)"
        )
    report = analytics.reliability.report
    print(
        f"\nPunctuality, last {report.window_days} days "
        f"(on time = within {report.on_time_minutes} min):"
    )
    scored = [(t, t.destination) for t in report.trains if t.destination]
    for t, d in sorted(scored, key=lambda pair: -pair[1].on_time_pct):
        tag = {"chronically_late": "  <- chronically late", "reliable": "  <- most reliable"}.get(
            t.label or "", ""
        )
        print(
            f"  {t.number} {t.name:<26} on time {d.on_time_pct:5.1f}%  "
            f"median {d.median:5.0f}  p90 {d.p90:5.0f}{tag}"
        )
    card = analytics.card
    print(
        f"\nForecast (quantile GBM), held out {card.test_start} to {card.test_end}: "
        f"MAE {card.mae_model:.1f} min "
        f"vs persistence {card.mae_persistence:.1f} ({card.mae_improvement_pct:.0f}% better), "
        f"p90 coverage {card.p90_coverage:.0%}"
    )


def print_chat(result: ChatResult) -> None:
    print(f"\n> {result.message}")
    print(f"  [{result.kind}] {result.answer}")
    if result.clarify and result.clarify.options:
        print("  options: " + " | ".join(o.label for o in result.clarify.options[:4]))
    if result.status and result.status.forecasts:
        nxt = result.status.forecasts[0]
        print(
            f"  card: {result.status.state}, {result.status.delay_min} min late at "
            f"{result.status.last_station}; "
            f"next {nxt.station} {nxt.eta_p50:%H:%M}-{nxt.eta_p90:%H:%M}"
        )
    if result.badge:
        b = result.badge
        print(
            f"  badge: {b.station} avg {b.mean:.0f} min late, "
            f"on time {b.on_time_pct:.0f}% (last {b.window_days} days)"
        )
    if result.dropped_claims:
        print(f"  ! {len(result.dropped_claims)} uncited claims dropped")


async def cmd_demo(container: Container, _: argparse.Namespace) -> int:
    await seed_demo(container)
    print_patterns(container)
    clock = container.live.now()
    print(
        f"\nLive feed ({container.live.source.name}), clock {clock:%Y-%m-%d %H:%M}: "
        f"{container.live.event_count()} events"
    )
    for message in container.catalog.chat.examples:
        print_chat(await container.chat.ask(message))
    # A clarifying question, then its answer: the context carries the station across.
    first = await container.chat.ask("Is my train to Kanpur late?")
    print_chat(first)
    print_chat(await container.chat.ask("22448", first.context))
    return 0


async def cmd_eval(container: Container, _: argparse.Namespace) -> int:
    samples = container.settings.samples_dir
    truth = json.loads((samples / "ground_truth.json").read_text("utf-8"))
    cases = json.loads((samples / "chat_eval.json").read_text("utf-8"))["cases"]
    await seed_demo(container)
    sections = await evaluate(container, truth, cases)
    passed = total = 0
    for section in sections:
        print(f"\n{section.name}  ({section.passed}/{len(section.checks)})")
        for check in section.checks:
            mark = "PASS" if check["passed"] else "FAIL"
            print(
                f"  {mark}  {check['check']}"
                + (f"  ({check['detail']})" if check["detail"] else "")
            )
        passed += section.passed
        total += len(section.checks)
    print(f"\nTotal: {passed}/{total}")
    return 0 if passed == total else 1


async def cmd_ask(container: Container, args: argparse.Namespace) -> int:
    await seed_demo(container)
    result = await container.chat.ask(args.message)
    print_chat(result)
    if args.json:
        print(result.model_dump_json(indent=2))
    return 0


async def cmd_train(container: Container, _: argparse.Namespace) -> int:
    if container.history.count() == 0:
        _err("No history in the database: run the server once, or `ingest --history FILE`.")
        return 1
    await container.analytics.build()
    print_patterns(container)
    return 0


async def cmd_ingest(container: Container, args: argparse.Namespace) -> int:
    if args.history:
        report = container.history.import_file(Path(args.history), replace=args.replace)
        print(report.model_dump_json(indent=2))
        return 0
    until = datetime.fromisoformat(args.until) if args.until else None
    while True:
        inserted = await container.live.poll_once(until)
        print(
            f"{container.live.last_poll:%Y-%m-%d %H:%M}: stored {inserted} new events "
            f"from {container.live.source.name}"
        )
        if not args.watch:
            return 0
        await asyncio.sleep(container.settings.live_poll_seconds or 5)


COMMANDS = {
    "demo": cmd_demo,
    "eval": cmd_eval,
    "ask": cmd_ask,
    "train": cmd_train,
    "ingest": cmd_ingest,
}
TEMPORARY = {"demo", "eval"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__.split("\n")[0])
    parser.add_argument("--fake", action="store_true", help="demo mode: no API key needed")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="seed, ingest, train, print the patterns and sample chats")
    sub.add_parser("eval", help="score against samples/ground_truth.json and chat_eval.json")
    ask = sub.add_parser("ask", help="ask the chatbot one message")
    ask.add_argument("message")
    ask.add_argument("--json", action="store_true", help="print the whole result as JSON")
    sub.add_parser("train", help="rebuild the analytics from the database's history")
    ingest = sub.add_parser("ingest", help="poll the live source, or import history")
    ingest.add_argument("--until", help="poll up to this time (ISO, e.g. 2026-11-27T18:00)")
    ingest.add_argument("--watch", action="store_true", help="keep polling every LIVE_POLL_SECONDS")
    ingest.add_argument("--history", help="import a history CSV (.csv or .csv.gz) instead")
    ingest.add_argument(
        "--replace", action="store_true", help="with --history: replace runs already stored"
    )
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    configure_logging("WARNING")
    overrides: dict[str, Any] = {"seed_demo": False, "live_poll_seconds": 0}
    if args.fake:
        overrides["llm_provider"] = "fake"

    async def go(settings: Settings) -> int:
        container = build_container(settings)
        container.runner.bind(asyncio.get_running_loop())
        try:
            return await COMMANDS[args.command](container, args)
        finally:
            await container.live.stop()
            await container.runner.shutdown()
            container.engine.dispose()

    if args.command in TEMPORARY:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            return asyncio.run(go(Settings(data_dir=Path(tmp), **overrides)))
    return asyncio.run(go(Settings(**overrides)))


if __name__ == "__main__":
    raise SystemExit(main())
