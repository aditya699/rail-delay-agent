# Samples

All simulated by [`server/scripts/make_samples.py`](../server/scripts/make_samples.py) (seeded; re-running it reproduces these files byte for byte). Station codes and coordinates are real and approximate; every train, number, name, timetable and delay is fictional.

| File | What it is |
| --- | --- |
| `history.csv.gz` | 2025-11-01 to 2026-11-25: one row per train, run date and stop, with scheduled and actual arrival and departure (IST). About 52,000 rows. What the analysis learns from |
| `live_replay.csv` | 2026-11-26 and 2026-11-27, same columns, held out of the history. The simulated live source replays it on an accelerated clock |
| `ground_truth.json` | What was planted: fog and monsoon months and stations, the DDU evening window, the least and most punctual trains, the unusual live event, the p90 coverage band. `python -m app.cli eval` scores against it |
| `chat_eval.json` | Labelled passenger messages (English and Hinglish): the intent to extract, or that a clarifying question is due |
