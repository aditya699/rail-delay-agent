import type { Badge } from "../../api/types";
import { MONTHS, delayTone } from "../../lib/format";

/** "Based on previous patterns, this train has been delayed on average X." */
export function HistoryBadge({ badge }: { badge: Badge }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-indigo-100 bg-indigo-50/60 px-4 py-3">
      <span aria-hidden className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">
        H
      </span>
      <div className="min-w-0 space-y-0.5">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-700">Based on previous patterns</p>
        <p className="text-sm text-zinc-800">
          At {badge.station_name} this train has been{" "}
          <span className={`font-semibold ${delayTone(badge.mean)}`}>{Math.round(badge.mean)} min late on average</span>{" "}
          over the last {badge.window_days} days.
        </p>
        <p className="text-xs text-zinc-600">
          Median {Math.round(badge.median)} min · bad day (p90) {Math.round(badge.p90)} min · on time on{" "}
          {Math.round(badge.on_time_pct)}% of {badge.n} runs
          {badge.month && badge.month_mean !== null
            ? ` · every ${MONTHS[badge.month - 1]} in the history: ${Math.round(badge.month_mean)} min`
            : ""}
        </p>
      </div>
    </div>
  );
}
