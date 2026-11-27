import { Badge, Spinner } from "../../components/ui";
import { useHealth } from "../../hooks/queries";
import { dayMonth, hhmm } from "../../lib/format";

/** Which model answers, the live feed's clock, and whether the models are still building. */
export function HealthBadge() {
  const health = useHealth();
  if (health.error) return <Badge className="bg-red-50 text-red-800">API unreachable</Badge>;
  if (!health.data) return null;
  const { llm_provider, model, analytics, live } = health.data;
  const demo = llm_provider === "fake";
  return (
    <div className="flex flex-wrap items-center gap-2">
      {analytics.state === "building" && (
        <Badge className="gap-1.5 bg-sky-50 text-sky-800">
          <Spinner className="h-3 w-3" /> Training on the history
        </Badge>
      )}
      {analytics.state === "failed" && <Badge className="bg-red-50 text-red-800">Analytics failed</Badge>}
      <Badge className="bg-zinc-100 text-zinc-700" >
        {live.source === "simulated" ? `Simulated feed · ${live.speed}x` : `Live: ${live.source}`} · {hhmm(live.clock)}{" "}
        {dayMonth(live.clock)}
      </Badge>
      <Badge className={demo ? "bg-amber-100 text-amber-900" : "bg-zinc-100 text-zinc-700"}>
        {demo ? "Demo mode (no API key)" : model}
      </Badge>
    </div>
  );
}
