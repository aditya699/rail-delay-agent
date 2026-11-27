# Data sources

Everything in `samples/` is simulated. This page covers what real data would look like, where it could come from, and where it must not come from.

## First, the rules

- **Indian Railways does not offer an official public API for live train running status.** NTES (National Train Enquiry System, run by CRIS) and IRCTC publish running status for passengers on their websites and apps, not as a data service.
- **Do not scrape NTES, IRCTC or similar sites.** Their terms do not permit automated collection, pages change without notice, and heavy polling of public-service infrastructure is both impolite and a quick way to get blocked. This repository contains no scraper and should not get one.
- **Use a source you are allowed to use**: a commercial running-status provider you have a contract or developer terms with, an official data-sharing arrangement, or data you collected yourself (your own journeys, a station's published arrival boards with permission). Read the terms, keep the request rate low, identify your client (`HTTP_USER_AGENT`), and cache.
- **Do not present the result as official.** No Indian Railways or IRCTC names or logos on a deployment; say where the data comes from.

## Running history (what the analysis learns from)

One row per train, run date and stop. The importer (`app/analysis/dataset.py::read_history_csv`, CLI `ingest --history`) reads `.csv` or `.csv.gz` with these columns:

| Column | Meaning |
| --- | --- |
| `run_date` | date the run left its origin, `YYYY-MM-DD` |
| `train_no` | train number, must exist in `network.json` |
| `seq` | stop index along the run, 0 = origin |
| `station` | station code, must exist in `network.json` |
| `sched_arr`, `act_arr` | scheduled and actual arrival, `YYYY-MM-DD HH:MM` IST (empty at the origin) |
| `sched_dep`, `act_dep` | scheduled and actual departure (empty at the destination) |

```bash
cd server
uv run python -m app.cli ingest --history my_runs.csv.gz            # skips runs already stored
uv run python -m app.cli ingest --history my_runs.csv.gz --replace  # overwrites them
uv run python -m app.cli train                                      # rebuild the analytics
```

Rows for unknown trains or stations are skipped and counted. Add the stations (code, name, coordinates, aliases) and trains (stops and timetable) to `server/app/config/network.json` first.

A year is the minimum for seasonality: with one winter you can describe fog, but not test a fog forecast on an unseen winter. Two or three years make the month effects far more trustworthy.

## Live running status

The app reads live data only through the `LiveSource` protocol in `app/ingest/live.py`:

```python
class LiveSource(Protocol):
    name: str
    def now(self) -> datetime: ...                        # IST, naive
    async def fetch(self, since, until) -> list[FeedEvent]: ...
```

### Simulated (default)

`SimulatedLiveSource` replays `samples/live_replay.csv` (26 and 27 Nov 2026, held out of the history) on `SimClock`. `LIVE_START` sets where the clock starts and `LIVE_SPEED` how fast it runs. It is the reference implementation: the eval checks the forecast and the unusual flag against what then "happens".

### Third-party running-status API (stub, off by default, unverified)

`RunningStatusApiSource` is a template for a provider you have access to. It has **not** been tested against any real service, and the URL shape below is an assumption, not a real API:

```
GET {RUNNING_STATUS_API_URL}/trains/{number}/runs/{YYYY-MM-DD}
Authorization: Bearer {RUNNING_STATUS_API_KEY}

{"stops": [{"seq": 0, "station": "NDLS", "sched_dep": "2026-11-27T16:55:00", "act_dep": "2026-11-27T17:02:00"},
           {"seq": 1, "station": "GZB", "sched_arr": "...", "act_arr": "...", "sched_dep": "...", "act_dep": "..."}]}
```

To use it:

1. Get access to a provider and read its terms (rate limits, caching, attribution, whether you may store the data).
2. Adapt `_parse` (and the URL in `fetch`) to the provider's real response.
3. In `server/.env`: `LIVE_SOURCE=http`, `RUNNING_STATUS_API_URL=...`, `RUNNING_STATUS_API_KEY=...`, and a `LIVE_POLL_SECONDS` the provider allows. It polls today's and yesterday's run of every train in `network.json` each tick, so 17 trains at 60 s is 34 requests a minute: raise the interval, or poll only trains someone asked about.
4. Write a test with a recorded response (`httpx.MockTransport`) before trusting it.

Provider station codes and train numbers may differ from yours; map them in `_parse`.

## Weather (an obvious next feature)

The month is a proxy for fog and rain. Real visibility and rainfall per section would replace it: the India Meteorological Department publishes observations and forecasts (check its data policy), and several open weather APIs offer historical data. Join on the nearest station and the hour.
