import type { StationReport } from "../../api/types";
import { Badge } from "../../components/ui";
import { heat } from "../../lib/format";

/** Added vs inherited, side by side: the bar a dashboard would show, split into its two causes. */
export function HotspotTable({ report, limit = 12 }: { report: StationReport; limit?: number }) {
  const rows = report.stations.slice(0, limit);
  const naive = report.stations.find((s) => s.code === report.naive_top);
  const shown = naive && !rows.includes(naive) ? [...rows, naive] : rows;
  const maxArrival = Math.max(...shown.map((s) => s.arrival_mean), 1);
  const maxAdded = Math.max(...report.stations.map((s) => s.added_mean), 1);
  const x = (v: number) => `${(Math.max(v, 0) / maxArrival) * 100}%`;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3 text-[11px] text-zinc-500">
        <span className="flex items-center gap-1">
          <span className="h-2 w-4 rounded-sm bg-orange-500" /> added approaching the station
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-4 rounded-sm bg-zinc-300" /> inherited from earlier stops
        </span>
        <span>Whiskers: 95% interval (bootstrap by day).</span>
      </div>
      <ul className="space-y-2">
        {shown.map((s) => (
          <li key={s.code} className="grid grid-cols-[22px_minmax(0,150px)_minmax(0,1fr)_88px] items-center gap-2 text-xs">
            <span className="text-right tabular-nums text-zinc-400">{s.rank}</span>
            <span className="min-w-0">
              <span className="block truncate font-medium text-zinc-800">
                {s.code} <span className="font-normal text-zinc-500">{s.name}</span>
              </span>
              {s.code === report.naive_top && (
                <Badge className="mt-0.5 bg-zinc-100 px-1.5 text-[10px] text-zinc-600">worst arrival delay, mostly inherited</Badge>
              )}
            </span>
            <span className="relative h-3 rounded-sm bg-zinc-50" title={`${s.arrival_mean.toFixed(1)} min mean arrival delay`}>
              <span className="absolute inset-y-0 left-0 rounded-l-sm bg-zinc-300" style={{ width: x(s.inherited_mean) }} />
              <span
                className="absolute inset-y-0 rounded-r-sm"
                style={{ left: x(s.inherited_mean), width: x(s.added_mean), background: heat(s.added_mean, maxAdded) }}
              />
            </span>
            <span className="text-right tabular-nums">
              <span className="font-semibold text-zinc-900">+{s.added_mean.toFixed(1)}</span>
              <span className="text-zinc-400">
                {" "}
                [{s.added_ci_low.toFixed(1)}–{s.added_ci_high.toFixed(1)}]
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
