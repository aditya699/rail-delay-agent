// Shapes of the API's JSON. Mirrors server/app/schemas/*.py and app/agents/chat.py.

export interface Health {
  status: string;
  llm_provider: "anthropic" | "fake";
  model: string;
  history_rows: number;
  analytics: { state: "empty" | "building" | "ready" | "failed"; error: string | null; seconds: number | null; as_of: string | null };
  live: {
    source: string;
    clock: string;
    speed: number;
    poll_seconds: number;
    last_poll: string | null;
    events: number;
  };
  background_tasks: number;
}

export interface Fact {
  id: string;
  label: string;
  value: number | string | boolean;
  unit: string;
}

export interface StopForecast {
  seq: number;
  station: string;
  station_name: string;
  sched_arr: string;
  p50_delay: number;
  p90_delay: number;
  eta_p50: string;
  eta_p90: string;
}

export type RunState = "not_started" | "running" | "arrived";

export interface LiveStatus {
  train_no: string;
  name: string;
  from_station: string;
  to_station: string;
  run_date: string;
  state: RunState;
  clock: string;
  last_station: string | null;
  last_station_name: string | null;
  last_event: "arr" | "dep" | null;
  last_event_at: string | null;
  delay_min: number | null;
  scheduled_departure: string | null;
  next_station: string | null;
  forecasts: StopForecast[];
  unusual: boolean;
  usual_median: number | null;
  usual_p90: number | null;
  source: string;
}

export interface Badge {
  train_no: string;
  station: string;
  station_name: string;
  window_days: number;
  n: number;
  mean: number;
  median: number;
  p90: number;
  on_time_pct: number;
  month: number | null;
  month_mean: number | null;
  month_n: number | null;
}

export interface StationStat {
  code: string;
  name: string;
  n: number;
  arrival_mean: number;
  inherited_mean: number;
  added_mean: number;
  added_ci_low: number;
  added_ci_high: number;
  added_p90: number;
  added_share: number | null;
  rank: number;
}

export interface StationReport {
  months: number[];
  stations: StationStat[];
  naive_top: string;
  facts: Fact[];
}

export interface HeatCell {
  station: string;
  month: number;
  n: number;
  added_mean: number;
}

export interface SeasonalStation {
  station: string;
  baseline: number;
  months: number[];
  peak_month: number;
  peak_added: number;
}

export interface HourCell {
  station: string;
  hour: number;
  n: number;
  added_mean: number;
}

export interface HourWindow {
  station: string;
  hours: number[];
  label: string;
  excess: number;
}

export interface SeasonalityReport {
  cells: HeatCell[];
  seasonal: SeasonalStation[];
  hours: HourCell[];
  windows: HourWindow[];
}

export interface DelayStats {
  n: number;
  mean: number;
  median: number;
  p90: number;
  on_time_pct: number;
}

export interface TrainReliability {
  number: string;
  name: string;
  from_station: string;
  to_station: string;
  destination: DelayStats | null;
  label: "chronically_late" | "reliable" | null;
}

export interface ReliabilityReport {
  as_of: string;
  window_start: string;
  window_days: number;
  on_time_minutes: number;
  trains: TrainReliability[];
  most_late: string;
  most_on_time: string;
}

export interface HorizonScore {
  bucket: string;
  n: number;
  mae_model: number;
  mae_persistence: number;
}

export interface ModelCard {
  trained_on: string;
  test_start: string;
  test_end: string;
  n_train: number;
  n_test: number;
  features: string[];
  mae_model: number;
  mae_persistence: number;
  mae_improvement_pct: number;
  p90_coverage: number;
  by_horizon: HorizonScore[];
}

export interface UnusualArrival {
  train_no: string;
  name: string;
  run_date: string;
  station: string;
  station_name: string;
  arrived_at: string;
  delay_min: number;
  usual_median: number;
  usual_p90: number;
}

export interface Station {
  code: string;
  name: string;
  lat: number;
  lon: number;
}

export interface Corridor {
  id: string;
  name: string;
  stations: string[];
}

export interface TrainInfo {
  number: string;
  name: string;
  kind: string;
  from_station: string;
  to_station: string;
  stops: { station: string; arr: string | null; dep: string | null }[];
}

export interface Network {
  stations: Station[];
  corridors: Corridor[];
  trains: TrainInfo[];
}

// --- Chat -----------------------------------------------------------------------

export type IntentKind = "train_status" | "train_history" | "hotspots" | "help";

export interface ChatIntent {
  kind: IntentKind;
  train_number: string | null;
  train_name: string | null;
  station: string | null;
  months: number[];
  language: "english" | "hinglish";
}

export interface Claim {
  text: string;
  fact_ids: string[];
}

export interface Option {
  label: string;
  value: string;
}

export interface ChatContext {
  train_number: string | null;
  station: string | null;
  pending: IntentKind | null;
}

export interface ChatResult {
  message: string;
  kind: IntentKind;
  intent: ChatIntent;
  answer: string;
  claims: Claim[];
  dropped_claims: string[];
  clarify: { question: string; options: Option[] } | null;
  train_number: string | null;
  station: string | null;
  status: LiveStatus | null;
  badge: Badge | null;
  hotspots: StationStat[];
  hotspot_months: number[];
  facts: Record<string, Fact>;
  context: ChatContext;
  model: string;
}
