// Display helpers for minutes, clock times, months and the delay colour scale.

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-11-27T14:05:00" -> "14:05" (times are IST from the server, no zone). */
export function hhmm(iso: string | null | undefined): string {
  if (!iso) return "–";
  const match = /T(\d\d:\d\d)/.exec(iso);
  return match?.[1] ?? iso;
}

/** "2026-11-27T14:05:00" -> "27 Nov". */
export function dayMonth(iso: string | null | undefined): string {
  if (!iso) return "";
  const [, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!m || !d) return iso;
  return `${d} ${MONTHS[m - 1]}`;
}

export function minutes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  return `${Math.round(value)} min`;
}

/** A delay in words: "on time", "4 min early", "34 min late". */
export function delayText(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  const rounded = Math.round(value);
  if (rounded <= 0) return rounded < -1 ? `${-rounded} min early` : "on time";
  return `${rounded} min late`;
}

/** Tailwind text colour for a delay in minutes (on-time margin is 15). */
export function delayTone(value: number | null | undefined): string {
  if (value === null || value === undefined) return "text-zinc-500";
  if (value <= 5) return "text-emerald-700";
  if (value <= 15) return "text-amber-700";
  if (value <= 45) return "text-orange-700";
  return "text-red-700";
}

export function delayChip(value: number | null | undefined): string {
  if (value === null || value === undefined) return "bg-zinc-100 text-zinc-600";
  if (value <= 5) return "bg-emerald-50 text-emerald-800";
  if (value <= 15) return "bg-amber-50 text-amber-800";
  if (value <= 45) return "bg-orange-50 text-orange-800";
  return "bg-red-50 text-red-800";
}

/** A warm sequential colour for added delay: pale at 0, deep red at `max`. */
export function heat(value: number, max: number): string {
  const t = Math.max(0, Math.min(1, max > 0 ? value / max : 0));
  const hue = 42 - 38 * t;
  const light = 96 - 50 * t;
  const sat = 70 + 20 * t;
  return `hsl(${hue.toFixed(0)} ${sat.toFixed(0)}% ${light.toFixed(0)}%)`;
}

export function pct(value: number, digits = 0): string {
  return `${value.toFixed(digits)}%`;
}

export function monthList(months: number[]): string {
  if (months.length === 0) return "all year";
  return months.map((m) => MONTHS[m - 1]).join(", ");
}
