import type { SeasonalityReport } from "../../api/types";

/** Mean added delay by scheduled arrival hour at one station, its seasonal months left out. */
export function HourChart({ report, station }: { report: SeasonalityReport; station: string }) {
  const cells = report.hours.filter((h) => h.station === station && h.n >= 10);
  const windows = report.windows.filter((w) => w.station === station);
  const inWindow = new Set(windows.flatMap((w) => w.hours));
  const width = 560;
  const height = 190;
  const top = 18;
  const bottom = 24;
  const slot = width / 24;
  const max = Math.max(...cells.map((c) => c.added_mean), 5);
  const min = Math.min(0, ...cells.map((c) => c.added_mean));
  const y = (v: number) => top + ((max - v) / (max - min)) * (height - top - bottom);
  if (cells.length === 0) {
    return <p className="text-sm text-zinc-500">No arrivals timetabled at {station} (it is only an origin).</p>;
  }
  return (
    <div className="space-y-2">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label={`Added delay by hour at ${station}`}>
        <line x1={0} x2={width} y1={y(0)} y2={y(0)} className="stroke-zinc-300" />
        {Array.from({ length: 24 }, (_, hour) => (
          <text key={hour} x={slot * hour + slot / 2} y={height - 6} textAnchor="middle" className="fill-zinc-400 text-[10px]">
            {hour % 3 === 0 ? String(hour).padStart(2, "0") : ""}
          </text>
        ))}
        {cells.map((c) => {
          const x = slot * c.hour + slot * 0.15;
          const y0 = y(Math.max(c.added_mean, 0));
          const y1 = y(Math.min(c.added_mean, 0));
          return (
            <g key={c.hour}>
              <title>
                {String(c.hour).padStart(2, "0")}:00: {c.added_mean.toFixed(1)} min added ({c.n} arrivals)
              </title>
              <rect
                x={x}
                y={y0}
                width={slot * 0.7}
                height={Math.max(1, y1 - y0)}
                rx={2}
                className={inWindow.has(c.hour) ? "fill-red-500" : "fill-zinc-400"}
              />
              <text x={x + slot * 0.35} y={y0 - 4} textAnchor="middle" className="fill-zinc-600 text-[10px]">
                {c.added_mean.toFixed(0)}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="text-xs text-zinc-600">
        {windows.length > 0
          ? windows.map((w) => `Trains due ${w.label} lose +${w.excess.toFixed(0)} min more than a typical hour here.`).join(" ")
          : "No hour of the day stands out here once its seasonal months are left out."}{" "}
        <span className="text-zinc-400">Only hours with timetabled arrivals have bars.</span>
      </p>
    </div>
  );
}
