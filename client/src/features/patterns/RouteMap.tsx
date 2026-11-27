import { useMemo } from "react";

import type { Network, StationStat } from "../../api/types";
import { heat } from "../../lib/format";

const WIDTH = 620;
const HEIGHT = 560;
const PAD = 34;

interface Placed {
  code: string;
  name: string;
  x: number;
  y: number;
  stat: StationStat | undefined;
}

interface Box {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

const overlaps = (a: Box, b: Box) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;

/**
 * Stations plotted from latitude and longitude (equirectangular, good enough at this scale),
 * corridors as lines, dot size and colour = mean delay added approaching the station.
 */
export function RouteMap({
  network,
  stations,
  selected,
  onSelect,
}: {
  network: Network;
  stations: StationStat[];
  selected: string | null;
  onSelect: (code: string) => void;
}) {
  const byCode = useMemo(() => new Map(stations.map((s) => [s.code, s])), [stations]);
  const max = Math.max(...stations.map((s) => s.added_mean), 1);

  const placed = useMemo(() => {
    const lats = network.stations.map((s) => s.lat);
    const lons = network.stations.map((s) => s.lon);
    const midLat = ((Math.min(...lats) + Math.max(...lats)) / 2) * (Math.PI / 180);
    const kx = Math.cos(midLat);
    const spanX = (Math.max(...lons) - Math.min(...lons)) * kx;
    const spanY = Math.max(...lats) - Math.min(...lats);
    const scale = Math.min((WIDTH - 2 * PAD) / spanX, (HEIGHT - 2 * PAD) / spanY);
    const out = new Map<string, Placed>();
    for (const s of network.stations) {
      out.set(s.code, {
        code: s.code,
        name: s.name,
        x: PAD + (s.lon - Math.min(...lons)) * kx * scale,
        y: PAD + (Math.max(...lats) - s.lat) * scale,
        stat: byCode.get(s.code),
      });
    }
    return out;
  }, [network.stations, byCode]);

  const radius = (stat: StationStat | undefined) => 3 + Math.sqrt(Math.max(stat?.added_mean ?? 0, 0)) * 2.3;

  // Greedy label placement: right, left, above, below; first spot that is free.
  const labels = useMemo(() => {
    const taken: Box[] = [...placed.values()].map((p) => {
      const r = radius(p.stat);
      return { x0: p.x - r, y0: p.y - r, x1: p.x + r, y1: p.y + r };
    });
    const out = new Map<string, { x: number; y: number; anchor: "start" | "end" | "middle" }>();
    const ordered = [...placed.values()].sort((a, b) => (b.stat?.added_mean ?? 0) - (a.stat?.added_mean ?? 0));
    for (const p of ordered) {
      const r = radius(p.stat);
      const w = p.code.length * 7 + 2;
      const candidates = [
        { x: p.x + r + 3, y: p.y + 4, anchor: "start" as const, box: { x0: p.x + r + 2, y0: p.y - 6, x1: p.x + r + 4 + w, y1: p.y + 6 } },
        { x: p.x - r - 3, y: p.y + 4, anchor: "end" as const, box: { x0: p.x - r - 4 - w, y0: p.y - 6, x1: p.x - r - 2, y1: p.y + 6 } },
        { x: p.x, y: p.y - r - 4, anchor: "middle" as const, box: { x0: p.x - w / 2, y0: p.y - r - 15, x1: p.x + w / 2, y1: p.y - r - 2 } },
        { x: p.x, y: p.y + r + 12, anchor: "middle" as const, box: { x0: p.x - w / 2, y0: p.y + r + 2, x1: p.x + w / 2, y1: p.y + r + 14 } },
        { x: p.x - r - 3, y: p.y - r - 2, anchor: "end" as const, box: { x0: p.x - r - 4 - w, y0: p.y - r - 13, x1: p.x - r - 2, y1: p.y - r } },
        { x: p.x - r - 3, y: p.y + r + 10, anchor: "end" as const, box: { x0: p.x - r - 4 - w, y0: p.y + r, x1: p.x - r - 2, y1: p.y + r + 12 } },
        { x: p.x + r + 3, y: p.y + r + 10, anchor: "start" as const, box: { x0: p.x + r + 2, y0: p.y + r, x1: p.x + r + 4 + w, y1: p.y + r + 12 } },
        { x: p.x - r - 22, y: p.y + 4, anchor: "end" as const, box: { x0: p.x - r - 23 - w, y0: p.y - 6, x1: p.x - r - 21, y1: p.y + 6 } },
      ];
      const spot = candidates.find((c) => !taken.some((t) => overlaps(t, c.box)));
      if (!spot) continue; // crowded (the Mumbai stations): the tooltip still names it
      taken.push(spot.box);
      out.set(p.code, { x: spot.x, y: spot.y, anchor: spot.anchor });
    }
    return out;
  }, [placed]);

  return (
    <div className="space-y-2">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" role="img" aria-label="Route map of added delay by station">
        <rect width={WIDTH} height={HEIGHT} rx={10} className="fill-zinc-50" />
        {network.corridors.map((corridor) => {
          const points = corridor.stations
            .map((code) => placed.get(code))
            .filter((p): p is Placed => p !== undefined)
            .map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`)
            .join(" ");
          return <polyline key={corridor.id} points={points} fill="none" className="stroke-zinc-300" strokeWidth={3} strokeLinejoin="round" />;
        })}
        {[...placed.values()]
          .sort((a, b) => (a.stat?.added_mean ?? 0) - (b.stat?.added_mean ?? 0))
          .map((p) => {
            const label = labels.get(p.code);
            const isSelected = p.code === selected;
            return (
              <g key={p.code} onClick={() => onSelect(p.code)} className="cursor-pointer">
                <title>
                  {p.name} ({p.code})
                  {p.stat
                    ? `: ${p.stat.added_mean.toFixed(1)} min added on approach, ${p.stat.inherited_mean.toFixed(1)} min inherited`
                    : ": origin only"}
                </title>
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={radius(p.stat)}
                  fill={p.stat ? heat(p.stat.added_mean, max) : "#e4e4e7"}
                  className={isSelected ? "stroke-indigo-600" : "stroke-white"}
                  strokeWidth={isSelected ? 2.5 : 1.5}
                />
                {label && (
                  <text
                    x={label.x}
                    y={label.y}
                    textAnchor={label.anchor}
                    className={`text-[11px] ${isSelected ? "fill-indigo-700 font-semibold" : "fill-zinc-600"}`}
                  >
                    {p.code}
                  </text>
                )}
              </g>
            );
          })}
      </svg>
      <div className="flex flex-wrap items-center gap-3 text-[11px] text-zinc-500">
        <span>Dot size and colour: mean delay added approaching the station.</span>
        <span className="flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: heat(0, max) }} /> 0
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: heat(max / 2, max) }} /> {(max / 2).toFixed(0)}
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: heat(max, max) }} /> {max.toFixed(0)} min
        </span>
        <span>Click a station for its hour-of-day profile.</span>
      </div>
    </div>
  );
}
