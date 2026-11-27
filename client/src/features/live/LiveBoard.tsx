import { Panel, Spinner } from "../../components/ui";
import { useBoard } from "../../hooks/queries";
import { delayChip, delayText, hhmm } from "../../lib/format";

/** Every train's state from the live feed, refreshed every few seconds. Click to ask about one. */
export function LiveBoard({ onPick }: { onPick: (number: string) => void }) {
  const board = useBoard();
  return (
    <Panel title="Running now" actions={board.isFetching ? <Spinner className="h-3 w-3 text-zinc-400" /> : null}>
      <ul className="-my-1 divide-y divide-zinc-100">
        {(board.data ?? []).map((s) => (
          <li key={s.train_no}>
            <button
              type="button"
              onClick={() => onPick(s.train_no)}
              className="flex w-full items-center justify-between gap-2 py-1.5 text-left hover:bg-zinc-50"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-zinc-800">
                  {s.train_no} <span className="font-normal text-zinc-500">{s.name}</span>
                </span>
                <span className="block truncate text-[11px] text-zinc-500">
                  {s.state === "not_started"
                    ? `departs ${s.from_station} ${hhmm(s.scheduled_departure)}`
                    : `${s.state === "arrived" ? "arrived" : s.last_event === "arr" ? "at" : "left"} ${s.last_station} ${hhmm(s.last_event_at)}`}
                </span>
              </span>
              {s.state === "not_started" ? (
                <span className="shrink-0 rounded px-1.5 py-0.5 text-[11px] text-zinc-500">not started</span>
              ) : (
                <span className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium ${delayChip(s.delay_min)}`}>
                  {delayText(s.delay_min)}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
