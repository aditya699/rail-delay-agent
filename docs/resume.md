# Putting this project on your resume

"Built a chatbot" is a weak line. This project is worth more because it has what data roles probe in an interview: messy event data, a metric that misleads (arrival delay) and the fix (added vs inherited), seasonality, uncertainty done right, a forecast with a fair baseline and a leak-free split, and an LLM that is not allowed to make numbers up.

## Resume lines (pick two or three, change the numbers to yours)

- Built a train-delay assistant that ingests live running events and a year of stop-level history, and answers status questions in English and Hinglish with the live delay, a p50-p90 arrival forecast and a punctuality badge.
- Separated delay **added** at each station from delay **inherited** from earlier stops, showing that the station with the worst arrival delay added under 10% of it; ranked true hotspots with day-level cluster-bootstrap intervals and found seasonal (fog, monsoon) and hour-of-day effects.
- Forecast arrival delay with gradient-boosted quantile models (p50/p90) on a time-based hold-out: 41% lower MAE than the persistence baseline, 92% coverage for the p90 band.
- Designed the LLM layer so the model only extracts a structured intent and phrases answers from named facts; unknown trains and ambiguous stations trigger clarifying questions, and sentences citing numbers that were not computed are removed automatically. FastAPI, React + TypeScript, offline tests and an eval harness against planted ground truth.

## Questions you should be ready for

1. **Why not rank stations by average arrival delay?** Delay propagates. A station at the end of a line inherits everything upstream. Arrival delay = inherited + added; only added says where time is lost.
2. **Why a cluster bootstrap?** Delays on the same day are correlated (fog, a blocked line). Resampling single arrivals treats correlated observations as independent and makes intervals too narrow. Resampling days respects the dependence.
3. **How did you find seasonal months without hardcoding winter?** Per station, months whose mean added delay is well above the station's median month. Median, so the bad months do not inflate the baseline.
4. **Why drop seasonal months before the hour-of-day analysis?** Fog is worst at night. Without that, night hours on the fog stretch look like an hour effect when it is a winter effect: a confounder.
5. **What is your baseline and why?** Persistence: "the train stays as late as it is now". It is what a status page implies, and it is surprisingly strong one stop ahead. The model's edge grows with distance.
6. **Why a time-based split?** Random splits leak: runs on the same foggy day land in train and test, and target-encoded station profiles would see the future. Hold out the last 90 days, compute profiles only from the training period.
7. **Why quantile models instead of one prediction?** Passengers plan around the late case. p50 is the ETA; p90 is "leave margin for this". Check calibration with coverage: about 90% of arrivals should be at or below the p90.
8. **What can't this tell you?** The test window has no fog, so the winter forecast is not validated on an unseen winter. Hour effects are confounded with which trains run at that hour. The data here is simulated.
9. **How do you stop the LLM from inventing a delay?** It never sees the database. It returns a structured intent; code validates the train and station and computes everything; the reply must cite fact ids, and sentences with unknown ids or numbers not in their facts are deleted.
10. **Why not scrape NTES?** No official public API, terms forbid it, and it is public infrastructure. The source is behind an interface; use a licensed provider.

## Make it yours

Change `make_samples.py` to a route you know (your daily commute, a Vande Bharat corridor, a suburban line), plant a pattern you have seen as a passenger, and check whether the analysis finds it. Then write up what fooled it.
