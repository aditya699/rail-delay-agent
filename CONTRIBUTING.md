# Contributing

Thanks for helping. Issues and pull requests are welcome, from typo fixes to new tools and data sources.

## Setup

Follow the Quickstart in the [README](README.md). Set `LLM_PROVIDER=fake` in `server/.env` if you do not want to spend API credits while developing; the tests never call the real API.

## Before you open a pull request

```bash
cd server
uv run ruff format .
uv run ruff check .
uv run pytest
uv run python -m app.cli --fake eval

cd ../client
npm run lint
npm run build
```

CI runs the same checks (except the eval, which the test suite also covers).

## Conventions

- **Layers**: routes in `app/api/` stay thin; statistics live in `app/analysis/`, the chat flow in `app/agents/`, orchestration in `app/services/`, live sources in `app/ingest/`. Only `app/llm/anthropic_client.py` imports the Anthropic SDK.
- **Numbers are Python**: anything that computes a delay, a time or a percentage is deterministic code that returns named facts. The model reads questions and phrases answers; it does not calculate.
- **Never guess a train**: resolution happens in code against `network.json`. When in doubt, ask the user.
- **Types everywhere**: type hints on every function, Pydantic models at every boundary, `strict` TypeScript in the client.
- **Prompts are files**: prompt text lives in `app/llm/prompts/*.md`.
- **Config is data**: stations, trains, thresholds and examples live in `app/config/*.json` or `.env`, not in code.
- **Tests use the FakeLLM and a frozen clock**: script the model with `FakeLLM(responders=...)`; build sources with `SimClock(..., speed=0)`.
- **Sample data stays simulated**, and no scraper of NTES, IRCTC or similar sites will be merged (see [docs/data-sources.md](docs/data-sources.md)).

## Commit messages

Short imperative subject ("Add a weather feature to the forecast"), and a body that says why when it is not obvious.
