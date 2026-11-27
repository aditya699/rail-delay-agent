import type { ModelCard } from "../../api/types";
import { dayMonth } from "../../lib/format";

/** The forecast's held-out score vs "the delay stays what it is now". */
export function ModelCardPanel({ card }: { card: ModelCard }) {
  const max = Math.max(...card.by_horizon.map((h) => h.mae_persistence), 1);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">Model MAE</p>
          <p className="text-2xl font-semibold text-zinc-900">{card.mae_model.toFixed(1)} min</p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">Persistence</p>
          <p className="text-2xl font-semibold text-zinc-400">{card.mae_persistence.toFixed(1)} min</p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">p90 coverage</p>
          <p className="text-2xl font-semibold text-zinc-900">{(card.p90_coverage * 100).toFixed(0)}%</p>
        </div>
      </div>
      <p className="text-xs text-zinc-600">
        {card.mae_improvement_pct.toFixed(0)}% lower error than assuming the current delay stays the same, on{" "}
        {card.n_test.toLocaleString("en-IN")} held-out forecasts ({dayMonth(card.test_start)} to {dayMonth(card.test_end)}, never
        seen in training). {(card.p90_coverage * 100).toFixed(0)}% of arrivals came in at or before the p90; 90% is the target.
      </p>
      <ul className="space-y-1.5">
        {card.by_horizon.map((h) => (
          <li key={h.bucket} className="grid grid-cols-[70px_minmax(0,1fr)] items-center gap-2 text-xs">
            <span className="text-zinc-600">{h.bucket}</span>
            <span className="space-y-0.5">
              <span className="flex items-center gap-2">
                <span className="h-2 rounded-sm bg-indigo-500" style={{ width: `${(h.mae_model / max) * 100}%` }} />
                <span className="tabular-nums text-zinc-700">{h.mae_model.toFixed(1)}</span>
              </span>
              <span className="flex items-center gap-2">
                <span className="h-2 rounded-sm bg-zinc-300" style={{ width: `${(h.mae_persistence / max) * 100}%` }} />
                <span className="tabular-nums text-zinc-400">{h.mae_persistence.toFixed(1)}</span>
              </span>
            </span>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-1">
        {card.features.map((f) => (
          <code key={f} className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-700">
            {f}
          </code>
        ))}
      </div>
    </div>
  );
}
