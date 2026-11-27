# Architecture

```
               ┌──────────── LiveSource (simulated replay | third-party API stub)
               │ poll every LIVE_POLL_SECONDS
               ▼
client ──HTTP──> FastAPI routes ──> services ──> live_events / run_stops (SQLite)
 (React)              │                │
                      │                └──> AnalyticsService ──> analysis/ (pandas, scikit-learn)
                      │                                              │ facts
                      └──> ChatAgent ──> LLMClient (Claude | Fake)   ▼
                              intent ─> resolve in code ─> tools ─> cited reply
```

## Layers

| Layer | Folder | Knows about |
| --- | --- | --- |
| Routes | `app/api/routes/` | HTTP only; thin, call a service |
| Services | `app/services/` | Importing history, building and caching the analytics, polling the live source, answering status questions, the demo seed, evaluation |
| Agent | `app/agents/` | The chat flow: intent, resolution, tools as facts, the citation check, the template writer |
| Analysis | `app/analysis/` | Statistics on DataFrames. No database writes, no HTTP, no LLM |
| Ingest | `app/ingest/live.py` | Where live events come from. Nothing else knows which source is behind it |
| LLM | `app/llm/` | One method, `structured(system, content, schema)`. Only `anthropic_client.py` imports the SDK |
| Config | `app/core/config.py`, `app/config/*.json` | Settings from `.env`; the network and thresholds as data |

The rule that keeps it honest: **numbers flow only upward from `analysis/` and the live feed**. The agent passes facts to the model; the model passes back an intent and sentences; code checks both.

## Startup

1. `create_app` builds the container: settings, catalog (`network.json`, `analysis.json`, `chat.json`), engine and schema, the LLM client, the live source, the services.
2. The lifespan submits the startup task to the in-process `TaskRunner`: import `samples/history.csv.gz` if `run_stops` is empty, then `AnalyticsService.build()`, then a first live poll. The API answers immediately; pattern endpoints return `503 not_ready` until the build is done, and `/api/health` shows the state.
3. `LiveService.start()` begins the poll loop.

## Building the analytics

`AnalyticsService.build_sync` runs in a worker thread (`asyncio.to_thread`), so requests keep flowing:

```
load_history (SQL -> DataFrame) -> prepare (delays, inherited, added)
  -> DelayForecaster.fit      # score on the last 90 days, then refit on all history
  -> station_profile          # all-year hotspots (month subsets computed on demand, cached)
  -> seasonality              # month heatmap, seasonal months, hour windows
  -> reliability              # per train and stop: on-time %, mean, median, p90
```

The result is an immutable `Analytics` object swapped in when complete, so readers never see a half-built state. `POST /api/patterns/rebuild` re-reads `analysis.json` and builds again.

## The live side

- `LiveSource.fetch(since, until)` returns `FeedEvent`s (train, run date, stop, arr or dep, scheduled, actual).
- `LiveService.poll_once` fetches from the last poll's time to the source's now, and inserts new events (unique on train, run date, stop, event), so re-polls after a restart are harmless.
- `LiveService.status(number)` reads that train's events for today's and yesterday's run (yesterday's, because overnight trains are still running), picks the running run (else one that arrived in the last 3 hours, else today's not-yet-started run), and adds the forecast for every stop ahead and the unusual flag.

**One poller only.** The poller runs inside the API process. With several API workers, set `LIVE_POLL_SECONDS=0` for them and run `uv run python -m app.cli ingest --watch` as a single separate process against the same database. For durable scheduling, run `cli ingest` from cron or a job scheduler.

**The simulated clock.** `SimClock` starts at `LIVE_START` and runs `LIVE_SPEED` times faster than real time. Every "now" in the live code comes from `source.now()`, so tests freeze it (`speed=0`) and the real API adapter uses the IST wall clock.

## A chat turn

```
POST /api/chat {message, context}
  -> parse:      llm.structured(ChatIntent)                    # prompts/intent.md
  -> resolve:    train in network.json? station unique and on the route?
                 no  -> ChatResult(clarify={question, options}, context={station, pending})
  -> tools:      live.status + forecast | reliability.badge | analytics.hotspots(months)
                 -> facts: [{id, label, value, unit}]
  -> reply:      llm.structured(ChatReply)                     # prompts/reply.md
  -> check:      drop claims citing unknown ids or numbers not in their facts
                 none left -> templates.write_reply(facts)
  -> ChatResult(answer, claims, status, badge, hotspots, facts cited, context)
```

The client sends `context` back with the next message. That is how "Which train?" followed by "22448" keeps the station from the first message, without server-side sessions.

## Errors

Services raise `AppError` subclasses (`NotFoundError` 404, `ConflictError` 409, `NotReadyError` 503, `LLMError` 502); one handler renders `{"error": {"code", "message"}}`. The Claude client turns SDK errors and refusals into `LLMError` with an actionable message.

## Tests

`tests/conftest.py` builds containers with the FakeLLM, a temporary SQLite database and a **frozen** simulated clock at 12:00 on 27 Nov 2026. A session fixture seeds and trains once and is shared read-only; the API fixture starts the real app with `TestClient`, exactly as a fresh clone does.
