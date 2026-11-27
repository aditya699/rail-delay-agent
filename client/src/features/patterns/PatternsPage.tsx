import { useState } from "react";

import { ErrorText, Notice, Panel, Spinner, selectClass } from "../../components/ui";
import { useHotspots, useModelCard, useNetwork, useReady, useReliability, useSeasonality, useUnusual } from "../../hooks/queries";
import { MONTHS, hhmm, monthList } from "../../lib/format";
import { Heatmap } from "./Heatmap";
import { HotspotTable } from "./HotspotTable";
import { HourChart } from "./HourChart";
import { ModelCardPanel } from "./ModelCardPanel";
import { ReliabilityTable } from "./ReliabilityTable";
import { RouteMap } from "./RouteMap";

const PRESETS: { label: string; months: number[] }[] = [
  { label: "All year", months: [] },
  { label: "Winter fog (Dec-Jan)", months: [12, 1] },
  { label: "Monsoon (Jul-Aug)", months: [7, 8] },
];

/** Where and when trains lose time, from a year of history. Every number is computed in Python. */
export function PatternsPage() {
  const [months, setMonths] = useState<number[]>([]);
  const [station, setStation] = useState("DDU");
  const ready = useReady();
  const network = useNetwork();
  const hotspots = useHotspots(months);
  const seasonality = useSeasonality();
  const reliability = useReliability();
  const card = useModelCard();
  const unusual = useUnusual();

  if (!ready) {
    return (
      <p className="flex items-center gap-2 text-sm text-zinc-500">
        <Spinner /> Building the delay models from the history…
      </p>
    );
  }

  const key = months.join(",");
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        {PRESETS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            onClick={() => setMonths(preset.months)}
            className={`rounded-full border px-3 py-1 text-xs font-medium ${
              preset.months.join(",") === key ? "border-zinc-900 bg-zinc-900 text-white" : "border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-100"
            }`}
          >
            {preset.label}
          </button>
        ))}
        <select
          className={selectClass}
          value={months.length === 1 ? String(months[0]) : ""}
          onChange={(e) => setMonths(e.target.value ? [Number(e.target.value)] : [])}
          aria-label="Month"
        >
          <option value="">One month…</option>
          {MONTHS.map((m, index) => (
            <option key={m} value={index + 1}>
              {m}
            </option>
          ))}
        </select>
        <span className="text-xs text-zinc-500">Map and ranking: {monthList(months)}</span>
      </div>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        <Panel title="Route map: delay added approaching each station">
          {network.data && hotspots.data ? (
            <RouteMap network={network.data} stations={hotspots.data.stations} selected={station} onSelect={setStation} />
          ) : (
            <Spinner />
          )}
        </Panel>
        <Panel title="Hotspots: added vs inherited delay">
          <ErrorText error={hotspots.error} />
          {hotspots.data && (
            <>
              <HotspotTable report={hotspots.data} />
              <p className="mt-3 text-xs leading-relaxed text-zinc-600">
                Ranking stations by arrival delay blames the end of the line: {hotspots.data.naive_top} looks worst, but almost all of
                its delay was inherited. Ranking by the delay added on the approach finds where time is actually lost.
              </p>
            </>
          )}
        </Panel>
      </div>

      <Panel title="Seasonality: mean added delay by month">
        {network.data && seasonality.data && <Heatmap network={network.data} report={seasonality.data} onSelect={setStation} />}
        <p className="mt-2 text-xs text-zinc-500">Outlined: months well above that station's typical month. Click a station code.</p>
      </Panel>

      <div className="grid items-start gap-5 lg:grid-cols-2">
        <Panel
          title={`Hour of day at ${station}`}
          actions={
            <select className={selectClass} value={station} onChange={(e) => setStation(e.target.value)} aria-label="Station">
              {(network.data?.stations ?? []).map((s) => (
                <option key={s.code} value={s.code}>
                  {s.code} {s.name}
                </option>
              ))}
            </select>
          }
        >
          {seasonality.data && <HourChart report={seasonality.data} station={station} />}
        </Panel>
        <Panel title="Arrival forecast vs the persistence baseline">{card.data && <ModelCardPanel card={card.data} />}</Panel>
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Panel title={`Punctuality at destination, last ${reliability.data?.window_days ?? 90} days`}>
          {reliability.data && <ReliabilityTable report={reliability.data} />}
        </Panel>
        <Panel title="Unusual today">
          {unusual.data && unusual.data.length === 0 && (
            <p className="text-sm text-zinc-500">Nothing yet: every reported arrival is within its train's usual range.</p>
          )}
          <ul className="space-y-2">
            {(unusual.data ?? []).map((u) => (
              <li key={`${u.train_no}-${u.station}-${u.run_date}`}>
                <Notice>
                  <span className="font-semibold">
                    {u.train_no} {u.name}
                  </span>{" "}
                  reached {u.station_name} at {hhmm(u.arrived_at)}, {u.delay_min} min late. Usually {Math.round(u.usual_median)} min
                  (bad day {Math.round(u.usual_p90)}).
                </Notice>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
