# Extending

## Add a station or a train (no code)

Edit `server/app/config/network.json`:

- `stations`: `code`, `name`, `lat`, `lon`, and `aliases` (old names, city names, spellings: "Allahabad", "Mughalsarai", "Baroda"). The chatbot matches names and aliases in any case, and codes when written in capitals.
- `ambiguous_names`: a name that means several stations (`"Mumbai": ["CSMT", "BCT"]`). The bot resolves it by the train's route, or asks.
- `corridors`: ordered station lists, used only to draw lines on the map and order the heatmap.
- `trains`: `number`, `name`, `kind`, `from`, `to`, and `stops` with `arr`/`dep` as `HH:MM`. Times that go backwards roll over midnight, so overnight timetables need no day field.

Then import history that includes the new train (`cli ingest --history`) and rebuild (`cli train`, or restart).

## Tune the analysis (no code)

`server/app/config/analysis.json`: the on-time margin, the badge window, bootstrap repetitions, how far above typical a month or hour must be to be reported, the unusual-today thresholds, and the forecast's size and test window. `POST /api/patterns/rebuild` applies changes without a restart.

## Plug in a live source

Implement `LiveSource` (`name`, `now()`, `async fetch(since, until)`) in `app/ingest/live.py`, then pick it in `build_source` in `app/container.py` behind a new `LIVE_SOURCE` value. Read [data-sources.md](data-sources.md) first. Test it with a recorded response.

## Add a chat tool

Say you want "which train is fastest from Delhi to Kanpur this evening?".

1. **Compute it** in `app/analysis/` from the timetable and the reliability index; return a typed result.
2. **Turn it into facts** in `app/agents/tools.py` (named ids, labels, units; times as strings).
3. **Teach the intent**: add a kind to `IntentKind` in `app/schemas/llm.py`, describe it in `app/llm/prompts/intent.md`, and add keyword rules to `app/llm/fake_parser.py` so demo mode understands it too.
4. **Route it** in `ChatAgent.ask` (`app/agents/chat.py`): resolve its arguments in code, ask when ambiguous.
5. **Write a template** in `app/agents/templates.py` (demo mode and the fallback both use it), and tell `prompts/reply.md` how to lead.
6. **Show it** in `client/src/features/chat/`, and add labelled messages to `samples/chat_eval.json`.

The citation check needs no change: it checks whatever facts you produce.

## Improve the forecast

`app/analysis/predict.py` is self-contained: `build_pairs` makes the features, `_fit` trains one model per quantile, `DelayForecaster.fit` scores and refits. Ideas, each testable with `cli eval`:

- **Section nowcast**: mean added delay by other trains on the same sections in the last 2 hours (needs live events at training time; build it from history by looking back within each day).
- **Weather**: visibility and rainfall near each section instead of the month.
- **Conformal calibration**: adjust the p90 on a calibration window so coverage holds exactly at 90%.
- **Other learners**: LightGBM or CatBoost with quantile objectives; keep the same split and baseline so the comparison is fair.

## Move to Postgres

Set `DATABASE_URL=postgresql+psycopg://...` and `uv add psycopg[binary]`. The schema is created with `create_all`; for a long-lived deployment, add Alembic migrations.

## Run the poller separately

Set `LIVE_POLL_SECONDS=0` on the API and run one `uv run python -m app.cli ingest --watch`. For many workers or durable jobs, the `TaskRunner` can be swapped for a real queue (Celery, RQ, Arq); the services only need `submit`.
