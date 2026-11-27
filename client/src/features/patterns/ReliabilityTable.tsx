import type { ReliabilityReport } from "../../api/types";
import { Badge } from "../../components/ui";
import { delayTone } from "../../lib/format";

/** Punctuality at the destination over the badge window, most reliable first. */
export function ReliabilityTable({ report }: { report: ReliabilityReport }) {
  const rows = [...report.trains]
    .filter((t) => t.destination)
    .sort((a, b) => (b.destination?.on_time_pct ?? 0) - (a.destination?.on_time_pct ?? 0));
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-zinc-500">
          <tr>
            <th className="py-1.5 font-medium">Train</th>
            <th className="py-1.5 font-medium">Route</th>
            <th className="py-1.5 text-right font-medium">On time</th>
            <th className="py-1.5 text-right font-medium">Median</th>
            <th className="py-1.5 text-right font-medium">p90</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => {
            const d = t.destination;
            if (!d) return null;
            return (
              <tr key={t.number} className="border-t border-zinc-100">
                <td className="py-1.5">
                  <span className="font-medium text-zinc-800">{t.number}</span> <span className="text-zinc-500">{t.name}</span>
                  {t.label === "chronically_late" && <Badge className="ml-1.5 bg-red-50 text-red-800">chronically late</Badge>}
                  {t.label === "reliable" && <Badge className="ml-1.5 bg-emerald-50 text-emerald-800">most reliable</Badge>}
                </td>
                <td className="py-1.5 text-zinc-500">
                  {t.from_station} → {t.to_station}
                </td>
                <td className="py-1.5 text-right">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-1.5 w-12 rounded-full bg-zinc-100">
                      <span className="block h-1.5 rounded-full bg-emerald-500" style={{ width: `${d.on_time_pct}%` }} />
                    </span>
                    <span className="w-9 tabular-nums">{d.on_time_pct.toFixed(0)}%</span>
                  </span>
                </td>
                <td className={`py-1.5 text-right tabular-nums ${delayTone(d.median)}`}>{Math.round(d.median)} min</td>
                <td className={`py-1.5 text-right tabular-nums ${delayTone(d.p90)}`}>{Math.round(d.p90)} min</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
