# API

All routes are under `/api`. Interactive docs: http://localhost:8000/docs. Errors share one shape:

```json
{ "error": { "code": "not_found", "message": "Train 99999 is not in this network." } }
```

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/health` | Liveness, LLM provider and model, history rows, analytics state, live clock and event count |
| GET | `/api/network` | Stations (with coordinates), corridors, every train's timetable |
| GET | `/api/chat/examples` | Example questions |
| POST | `/api/chat` | A message (and the previous `context`) in; a clarifying question, or an answer with status, badge and facts out |
| GET | `/api/trains/{number}/status` | Live status with the forecast to every stop ahead, and the destination badge. 404 for unknown trains |
| GET | `/api/live/board` | Every train's state and delay, no forecasts |
| GET | `/api/live/unusual` | Today's arrivals far later than that train usually is at that stop |
| POST | `/api/live/poll` | Poll the live source now |
| GET | `/api/patterns/hotspots?months=12&months=1` | Stations ranked by added delay, with intervals; all year without `months` |
| GET | `/api/patterns/seasonality` | Month x station cells, seasonal months, hour-of-day cells and windows |
| GET | `/api/patterns/reliability` | Punctuality per train at its destination, last 90 days |
| GET | `/api/patterns/model` | The forecast's held-out score vs persistence |
| POST | `/api/patterns/rebuild` | Re-read `analysis.json` and rebuild in the background. 202 |

Pattern endpoints return `503 not_ready` while the models are building.

## Chat

```http
POST /api/chat
{"message": "Is my train to Kanpur late?", "context": null}
```

```json
{
  "kind": "train_status",
  "answer": "Which train? Send its 5-digit number (or its name).",
  "clarify": {
    "question": "Which train? Send its 5-digit number (or its name).",
    "options": [{"label": "22447 Purvai Superfast (New Delhi to Howrah Jn)", "value": "22447"}, "..."]
  },
  "context": {"train_number": null, "station": "CNB", "pending": "train_status"},
  "status": null, "badge": null, "facts": {}
}
```

Send the option's `value` (or anything the user types) with that `context`:

```http
POST /api/chat
{"message": "22448", "context": {"train_number": null, "station": "CNB", "pending": "train_status"}}
```

```json
{
  "kind": "train_status",
  "intent": {"kind": "train_status", "train_number": "22448", "train_name": null, "station": null, "months": [], "language": "english"},
  "train_number": "22448",
  "station": "CNB",
  "answer": "Purvai Superfast (22448) arrived at Asansol Jn at 12:01 and is running 6 min late. Expect it at Kanpur Central around 02:41, 28 Nov, ...",
  "claims": [{"text": "Purvai Superfast (22448) arrived at Asansol Jn at 12:01 ...", "fact_ids": ["train.name", "train.number", "live.last_station_name", "live.last_event_at", "live.last_event", "live.delay_min"]}],
  "dropped_claims": [],
  "status": {
    "train_no": "22448", "state": "running", "run_date": "2026-11-27",
    "last_station": "ASN", "last_event": "arr", "last_event_at": "2026-11-27T12:01:00", "delay_min": 6,
    "next_station": "JSME", "unusual": false, "usual_median": 7.0, "usual_p90": 14.1,
    "forecasts": [{"seq": 3, "station": "JSME", "sched_arr": "2026-11-27T13:40:00", "p50_delay": 7, "p90_delay": 11,
                   "eta_p50": "2026-11-27T13:47:00", "eta_p90": "2026-11-27T13:51:00"}, "..."]
  },
  "badge": {"station": "CNB", "window_days": 90, "n": 90, "mean": 40.2, "median": 33.0, "p90": 72.0, "on_time_pct": 13.3,
            "month": 11, "month_mean": 39.0, "month_n": 55},
  "facts": {"live.delay_min": {"id": "live.delay_min", "label": "Delay now", "value": 6, "unit": "min"}, "...": "..."},
  "context": {"train_number": "22448", "station": "CNB", "pending": null}
}
```

(Numbers above are illustrative; run it to see the real ones.)

`kind` is `train_status`, `train_history`, `hotspots` or `help`. `facts` holds only the facts the kept sentences cite. `dropped_claims` lists sentences removed by the citation check.

## Fact ids

| Prefix | From |
| --- | --- |
| `train.*` | the timetable: `number`, `name`, `from`, `to` |
| `live.*` | the live status: `state`, `clock`, `last_station_name`, `last_event`, `last_event_at`, `delay_min`, `unusual`, `usual_median`, `usual_p90`, `scheduled_departure` |
| `live.next.*`, `live.target.*`, `live.destination.*` | a forecast: `station_name`, `sched`, `eta_p50`, `eta_p90`, `p50_delay`, `p90_delay` |
| `badge.*` | `station_name`, `window_days`, `n`, `mean`, `median`, `p90`, `on_time_pct`, `on_time_minutes`, `month`, `month_mean` |
| `hotspots.*` | `period`, `{rank}.station`, `{rank}.name`, `{rank}.added`, `{rank}.ci_low`, `{rank}.ci_high`, `naive_top`, `naive_top.arrival`, `naive_top.added`, `naive_top.inherited` |
