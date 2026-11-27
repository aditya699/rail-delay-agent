import { useMemo } from "react";

import type { Network, SeasonalityReport } from "../../api/types";
import { MONTHS, heat } from "../../lib/format";

/** Month x station mean added delay. Outlined cells: months flagged seasonal for that station. */
export function Heatmap({
  network,
  report,
  onSelect,
}: {
  network: Network;
  report: SeasonalityReport;
  onSelect: (code: string) => void;
}) {
  const { rows, cells, seasonal, max } = useMemo(() => {
    const cells = new Map(report.cells.map((c) => [`${c.station}:${c.month}`, c]));
    const withData = new Set(report.cells.map((c) => c.station));
    const ordered: string[] = [];
    for (const corridor of network.corridors) {
      for (const code of corridor.stations) {
        if (withData.has(code) && !ordered.includes(code)) ordered.push(code);
      }
    }
    for (const code of withData) if (!ordered.includes(code)) ordered.push(code);
    const seasonal = new Set(report.seasonal.flatMap((s) => s.months.map((m) => `${s.station}:${m}`)));
    const max = Math.max(...report.cells.map((c) => c.added_mean), 1);
    return { rows: ordered, cells, seasonal, max };
  }, [network.corridors, report]);

  const names = new Map(network.stations.map((s) => [s.code, s.name]));
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-0.5 text-[11px]">
        <thead>
          <tr>
            <th className="w-14" />
            {MONTHS.map((m) => (
              <th key={m} className="font-medium text-zinc-500">
                {m}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((code) => (
            <tr key={code}>
              <th className="pr-1 text-left font-medium text-zinc-700">
                <button type="button" onClick={() => onSelect(code)} title={names.get(code)} className="hover:text-indigo-700">
                  {code}
                </button>
              </th>
              {MONTHS.map((_, index) => {
                const month = index + 1;
                const cell = cells.get(`${code}:${month}`);
                const flagged = seasonal.has(`${code}:${month}`);
                return (
                  <td
                    key={month}
                    title={cell ? `${names.get(code)}, ${MONTHS[index]}: ${cell.added_mean.toFixed(1)} min added (${cell.n} arrivals)` : ""}
                    className={`h-6 min-w-9 rounded-sm text-center tabular-nums ${flagged ? "outline outline-2 -outline-offset-2 outline-zinc-900" : ""}`}
                    style={{ background: cell ? heat(cell.added_mean, max) : "#fafafa" }}
                  >
                    <span className={cell && cell.added_mean > max * 0.55 ? "text-white" : "text-zinc-700"}>
                      {cell && Math.abs(cell.added_mean) >= 3 ? Math.round(cell.added_mean) : ""}
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
