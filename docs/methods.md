# The methods, in plain words

Every number the chatbot says comes from `server/app/analysis/`. None of it uses the language model. This page explains each step for someone who knows pandas but has not worked with transport data.

## The data shape

One row per train, run date and stop: scheduled and actual arrival and departure (IST). A **run** is one journey of one train, named by the date it leaves its origin; an overnight train's run of 26 Nov arrives on 27 Nov. From that, `dataset.py` derives per stop:

| Column | Meaning |
| --- | --- |
| `arr_delay` | actual minus scheduled arrival, in minutes. What a passenger on the platform sees |
| `dep_delay` | actual minus scheduled departure |
| `inherited` | the departure delay at the previous stop: the delay the train **brought with it** |
| `added` | `arr_delay - inherited`: the delay **gained on the approach** to this stop |
| `km` | section length (straight-line distance x 1.22, a rough track factor) |
| `month`, `hour` | of the scheduled arrival |

Feeds have gaps. A missing actual time drops that arrival (and the next stop's `inherited`), never the whole run.

## 1. Added vs inherited: which stations cause delay (`stations.py`)

Delay propagates. A train that leaves DDU 40 minutes late arrives at Patna 40 minutes late even if the Patna section ran perfectly. So the station with the worst **arrival** delay is usually near the end of a line, and it is rarely the cause. In the demo, Ara Jn has the worst mean arrival delay (60 min) but adds 4 of them; DDU adds 22.

The ranking is by mean `added`. A dashboard that ranks by arrival delay sends the operations team to the wrong place.

**Intervals.** The 95% interval of each station's mean added delay is a **cluster bootstrap by date**: resample whole days with replacement (400 times), recompute the mean, take the 2.5th and 97.5th percentiles. Why days and not single arrivals? Delays on the same day are correlated: a foggy night slows every train on the stretch. Resampling arrivals would treat 15 trains on one foggy night as 15 independent pieces of evidence and give an interval that is too narrow. `test_analysis.py` checks that the cluster interval is wider than the naive one on correlated data.

Restricted to some months (`?months=1`), the same ranking answers "which stations cause the most delay in January?".

## 2. When: months and hours (`seasonality.py`)

**Month x station heatmap** of mean added delay. A month is **seasonal** for a station when its mean is at least `season.min_excess_min` (8 min) above the station's **median** month, with at least 30 arrivals. The median, so the bad months do not raise their own bar. On the demo data this finds Dec and Jan on the fog stretch and Jul and Aug on the Konkan stretch, and nothing anywhere else.

**Hour of day**: mean added delay by scheduled arrival hour, with each station's seasonal months **left out**. Fog is densest at night, so without that step Kanpur would show a "night-time problem" that is really a winter problem. An hour is a problem window when it is `hour.min_excess_min` (10 min) above the station's median hour. The demo finds DDU 18:00-21:00 and no other station.

A station only has the hours its trains are timetabled at. Read a window as "trains due here 18:00-21:00 lose time", not as a 24-hour curve. With few trains per station, an hour effect and a train effect can look alike; a real analysis would fit station x hour and train together (a regression with both, or a mixed model).

## 3. Punctuality and the badge (`reliability.py`)

For each train and stop, over the last 90 days of history (`badge_window_days`):

- **on-time %**: share of arrivals within 15 minutes (`on_time_minutes`; a common margin in Indian Railways punctuality reporting),
- **mean, median and p90** arrival delay. Delays are skewed (most runs a few minutes late, a few runs hours late), so the mean alone overstates a typical day and hides a bad one. The badge shows all three.

Plus the same per calendar month across all history, because the last 90 days of a November badge contain no fog: "every December in the history: 74 min" is the honest seasonal warning.

The **least punctual** train (lowest on-time %, ties broken by higher mean) and the **most punctual** are labelled. In the demo: 13427 at 0%, 22973 at 100%.

## 4. Arrival forecast (`predict.py`)

**Question.** The train just left stop *k* with *d* minutes of delay. How late will it be at stop *j*?

**Training rows.** Every (run, *k*, *j > k*) pair in history: about 460,000 pairs, of which 40,000 are sampled to fit (configurable). Target: arrival delay at *j*.

**Features**, all known at prediction time:

| Feature | Why |
| --- | --- |
| `current_delay` | delay propagates, so this is the strongest predictor |
| `stops_ahead`, `km_ahead` | more distance, more noise and more chances to recover |
| `month`, `target_hour` | calendar position |
| `exp_added_month` | sum over the stops between *k* and *j* of each station's historical mean added delay **in that month**: "fog ahead", "monsoon ahead" |
| `exp_added_hour` | the same **by scheduled hour**: "DDU at 19:00 ahead" |
| `train_added_per_stop` | the train's own habit (chronic lateness) |
| `is_terminal` | timetables pad the last section, so trains recover some delay there |

The station profiles are target-style encodings, so they are computed **only from the training period** when scoring.

**Models.** Two gradient-boosted tree models with a quantile (pinball) loss: scikit-learn's `HistGradientBoostingRegressor(loss="quantile", quantile=0.5)` for the median and `quantile=0.9` for the late case. The p50 is the ETA; p50 to p90 is the band. If the p90 model ever predicts below the p50 (quantile crossing), the p90 is raised to the p50. A live train that is already later than its p50 at the next stop has that ETA pinned to "now".

**Evaluation.** A **time-based split**: the last 90 days of history are held out; profiles and models are fitted on everything before. A random split would leak, because runs on the same foggy day would sit on both sides. Metrics on the held-out pairs:

- **MAE** of the p50 vs the **persistence baseline** ("the delay stays what it is now"), overall and by how many stops ahead. Persistence is the right baseline: it is what a running-status page implicitly tells you.
- **p90 coverage**: the share of arrivals at or below the predicted p90. It should be close to 90%; much lower means the band is too optimistic, much higher means it is too wide to be useful.

On the demo data: MAE 10.6 vs 17.8 minutes (41% lower), and the gap widens with distance (7+ stops ahead: 21 vs 41). p90 coverage 92%. After scoring, everything is refitted on all history for serving. The eval also scores forecasts made at every departure in the live replay against what then happened.

Note the honest limit: the held-out period (Aug-Nov) has no fog. With one winter of history, you cannot test a fog forecast on an unseen winter. Say so in an interview.

## 5. "Unusual today" (`unusual.py`)

Today's delay at a stop is unusual when it is more than **15 minutes above** that train's p90 there **and** more than **30 minutes above** its median, with at least 10 runs of history. Both, so a train that is always very late is not flagged for being very late, and a train with a tight history is not flagged for being 8 minutes off. In the live replay, 10147 at Ratnagiri (80 minutes late where it is usually close to on time) is flagged, and so are its next two stops, because it carries the delay with it. No other train is flagged. The rule works on arrival delay, which is what a passenger feels; flagging on *added* delay instead would point at the one section where it happened.

## 6. How the chatbot stays honest (`app/agents/`)

- The model's first job is structured output only: kind of question, train number **as written**, station **as written**, months, language. It is told never to fill in a number the user did not write.
- Code resolves it against `network.json`. Unknown train, a name shared by both directions, an ambiguous city ("Mumbai": CSMT or Mumbai Central) that the route cannot settle, or a station the train does not stop at: the bot asks, with buttons. Context carries what is known ("Kanpur") into the next turn.
- Tools return **facts**: `live.delay_min`, `live.next.eta_p50`, `badge.on_time_pct`, `hotspots.1.station`, each with a label and unit. Times are facts too.
- The reply is a list of claims, each citing fact ids. `citations.py` drops a claim that cites nothing, cites an unknown id, or contains a number that is not among the values of the facts it cites (allowing rounding). If nothing survives, a deterministic template writes the answer from the same facts.
