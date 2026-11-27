import type { LiveStatus, StopForecast } from "../../api/types";
import { Badge } from "../../components/ui";
import { dayMonth, delayChip, delayText, delayTone, hhmm } from "../../lib/format";

const STATE_LABEL = { running: "Running", arrived: "Arrived", not_started: "Not started" } as const;
const STATE_TONE = {
  running: "bg-sky-50 text-sky-800",
  arrived: "bg-zinc-100 text-zinc-700",
  not_started: "bg-zinc-100 text-zinc-600",
} as const;

/** Minutes between two IST timestamps. */
function gap(from: string, to: string): number {
  return (new Date(to).getTime() - new Date(from).getTime()) / 60000;
}

/** Scheduled time, then the likely (p50) to late-case (p90) window, on one small timeline. */
export function EtaBand({ item }: { item: StopForecast }) {
  const span = Math.max(gap(item.sched_arr, item.eta_p90), 20);
  const left = (minutes: number) => `${Math.max(0, Math.min(100, (minutes / span) * 100))}%`;
  const p50 = gap(item.sched_arr, item.eta_p50);
  const p90 = gap(item.sched_arr, item.eta_p90);
  return (
    <div className="space-y-1">
      <div className="relative h-2 rounded-full bg-zinc-100">
        <div
          className="absolute top-0 h-2 rounded-full bg-amber-300"
          style={{ left: left(p50), width: `calc(${left(p90)} - ${left(p50)} + 4px)` }}
        />
        <div className="absolute -top-0.5 h-3 w-0.5 bg-zinc-500" style={{ left: "0%" }} title="Scheduled" />
        <div className="absolute -top-1 h-4 w-1 rounded bg-amber-600" style={{ left: left(p50) }} title="Likely (p50)" />
      </div>
      <div className="flex justify-between text-[11px] text-zinc-500">
        <span>due {hhmm(item.sched_arr)}</span>
        <span>
          likely <span className="font-semibold text-zinc-800">{hhmm(item.eta_p50)}</span> · late case{" "}
          <span className="font-semibold text-zinc-800">{hhmm(item.eta_p90)}</span>
        </span>
      </div>
    </div>
  );
}

function RouteStrip({ status, stops }: { status: LiveStatus; stops: string[] }) {
  const current = status.last_station ? stops.indexOf(status.last_station) : -1;
  return (
    <ol className="flex items-start gap-0 overflow-x-auto pb-1" aria-label="Route">
      {stops.map((code, index) => {
        const passed = index < current || (index === current && status.last_event === "dep");
        const here = index === current;
        return (
          <li key={code} className="flex min-w-9 flex-1 flex-col items-center">
            <div className="flex w-full items-center">
              <span className={`h-0.5 flex-1 ${index === 0 ? "bg-transparent" : passed || here ? "bg-zinc-800" : "bg-zinc-200"}`} />
              <span
                className={`h-2.5 w-2.5 shrink-0 rounded-full border-2 ${
                  here ? "border-amber-500 bg-amber-400" : passed ? "border-zinc-800 bg-zinc-800" : "border-zinc-300 bg-white"
                }`}
              />
              <span
                className={`h-0.5 flex-1 ${index === stops.length - 1 ? "bg-transparent" : passed ? "bg-zinc-800" : "bg-zinc-200"}`}
              />
            </div>
            <span className={`mt-1 text-[10px] ${here ? "font-semibold text-zinc-900" : "text-zinc-500"}`}>{code}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** The live status card: where the train is, how late, and when it reaches the next stop. */
export function StatusCard({ status, stops, highlight }: { status: LiveStatus; stops: string[]; highlight?: string | null }) {
  const next = status.forecasts[0];
  const target = highlight ? status.forecasts.find((f) => f.station === highlight) : undefined;
  return (
    <div className="space-y-3 rounded-lg border border-zinc-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-zinc-900">
            {status.name} <span className="font-normal text-zinc-500">· {status.train_no}</span>
          </p>
          <p className="text-xs text-zinc-500">
            {status.from_station} → {status.to_station} · run of {dayMonth(status.run_date)}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {status.unusual && <Badge className="bg-red-100 text-red-800">Unusual today</Badge>}
          <Badge className={STATE_TONE[status.state]}>{STATE_LABEL[status.state]}</Badge>
        </div>
      </div>

      {status.state === "not_started" ? (
        <p className="text-sm text-zinc-700">
          Departs {status.from_station} at <span className="font-semibold">{hhmm(status.scheduled_departure)}</span>. No
          departure reported yet.
        </p>
      ) : (
        <div className="flex flex-wrap items-end gap-x-6 gap-y-1">
          <p className={`text-2xl font-semibold tracking-tight ${delayTone(status.delay_min)}`}>{delayText(status.delay_min)}</p>
          <p className="pb-1 text-sm text-zinc-600">
            {status.last_event === "arr" ? "arrived at" : "left"} <span className="font-medium">{status.last_station_name}</span> at{" "}
            {hhmm(status.last_event_at)}
          </p>
        </div>
      )}
      {status.unusual && status.usual_median !== null && (
        <p className="rounded-md bg-red-50 px-3 py-1.5 text-xs text-red-800">
          Far worse than usual here: this train is normally {Math.round(status.usual_median)} min late at {status.last_station}{" "}
          (bad day: {Math.round(status.usual_p90 ?? 0)} min).
        </p>
      )}

      {stops.length > 0 && <RouteStrip status={status} stops={stops} />}

      {next && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-zinc-600">
            Next stop: <span className="text-zinc-900">{next.station_name}</span>
          </p>
          <EtaBand item={next} />
        </div>
      )}
      {target && target !== next && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-zinc-600">
            Your station: <span className="text-zinc-900">{target.station_name}</span>
          </p>
          <EtaBand item={target} />
        </div>
      )}
      {status.forecasts.length > 1 && (
        <details className="text-xs">
          <summary className="cursor-pointer font-medium text-indigo-700">All stops ahead (p50 to p90 forecast)</summary>
          <table className="mt-2 w-full text-left">
            <thead className="text-zinc-500">
              <tr>
                <th className="py-1 font-medium">Station</th>
                <th className="py-1 font-medium">Due</th>
                <th className="py-1 font-medium">Likely</th>
                <th className="py-1 font-medium">Late case</th>
                <th className="py-1 text-right font-medium">Delay</th>
              </tr>
            </thead>
            <tbody>
              {status.forecasts.map((f) => (
                <tr key={f.seq} className={`border-t border-zinc-100 ${f.station === highlight ? "bg-amber-50" : ""}`}>
                  <td className="py-1">{f.station_name}</td>
                  <td className="py-1 text-zinc-500">
                    {hhmm(f.sched_arr)} <span className="text-[10px]">{dayMonth(f.sched_arr)}</span>
                  </td>
                  <td className="py-1 font-medium">{hhmm(f.eta_p50)}</td>
                  <td className="py-1">{hhmm(f.eta_p90)}</td>
                  <td className="py-1 text-right">
                    <span className={`rounded px-1.5 py-0.5 ${delayChip(f.p50_delay)}`}>
                      {f.p50_delay}–{f.p90_delay} min
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
      <p className="text-[11px] text-zinc-400">
        Feed: {status.source} · clock {hhmm(status.clock)} {dayMonth(status.clock)}
      </p>
    </div>
  );
}
