import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import type { ChatContext, ChatResult } from "../../api/types";
import { Button, ErrorText, inputClass, Notice, Panel, Spinner } from "../../components/ui";
import { useAsk, useChatExamples, useNetwork } from "../../hooks/queries";
import { monthList } from "../../lib/format";
import { LiveBoard } from "../live/LiveBoard";
import { HistoryBadge } from "./HistoryBadge";
import { StatusCard } from "./StatusCard";

type Turn = { id: number; role: "user"; text: string } | { id: number; role: "bot"; result: ChatResult };

function HotspotMini({ result }: { result: ChatResult }) {
  if (result.hotspots.length === 0) return null;
  const max = Math.max(...result.hotspots.map((s) => s.added_mean), 1);
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-3">
      <p className="mb-2 text-xs font-medium text-zinc-600">Delay added approaching each station, {monthList(result.hotspot_months)}</p>
      <ul className="space-y-1.5">
        {result.hotspots.map((s) => (
          <li key={s.code} className="grid grid-cols-[110px_minmax(0,1fr)_64px] items-center gap-2 text-xs">
            <span className="truncate font-medium text-zinc-800" title={s.name}>
              {s.code} <span className="font-normal text-zinc-500">{s.name}</span>
            </span>
            <span className="h-2 rounded-full bg-zinc-100">
              <span className="block h-2 rounded-full bg-orange-500" style={{ width: `${(s.added_mean / max) * 100}%` }} />
            </span>
            <span className="text-right tabular-nums text-zinc-700">{s.added_mean.toFixed(1)} min</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function BotTurn({
  result,
  stopsFor,
  onOption,
  disabled,
}: {
  result: ChatResult;
  stopsFor: (number: string) => string[];
  onOption: (value: string) => void;
  disabled: boolean;
}) {
  const facts = Object.values(result.facts);
  return (
    <div className="max-w-[720px] space-y-3">
      <div className="rounded-2xl rounded-tl-sm border border-zinc-200 bg-white px-4 py-3">
        <p className="text-[15px] leading-relaxed text-zinc-900">{result.answer}</p>
        {result.clarify && result.clarify.options.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {result.clarify.options.map((option) => (
              <button
                key={option.value}
                type="button"
                disabled={disabled}
                onClick={() => onOption(option.value)}
                className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-800 hover:bg-indigo-100 disabled:opacity-50"
              >
                {option.label}
              </button>
            ))}
          </div>
        )}
      </div>
      {result.status && <StatusCard status={result.status} stops={stopsFor(result.status.train_no)} highlight={result.station} />}
      {result.badge && <HistoryBadge badge={result.badge} />}
      <HotspotMini result={result} />
      {result.dropped_claims.length > 0 && (
        <Notice>
          {result.dropped_claims.length} sentence(s) from the model were removed because they cited numbers that were not computed.
        </Notice>
      )}
      {facts.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer font-medium text-indigo-700">
            {facts.length} facts behind this answer · intent: {result.intent.kind}
            {result.intent.language === "hinglish" ? " (Hinglish)" : ""}
          </summary>
          <dl className="mt-2 grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-0.5 rounded-md bg-zinc-50 p-3 font-mono text-[11px]">
            {facts.map((f) => (
              <div key={f.id} className="contents">
                <dt className="truncate text-zinc-500" title={f.label}>
                  {f.id}
                </dt>
                <dd className="text-right text-zinc-800">
                  {String(f.value)}
                  {f.unit ? ` ${f.unit}` : ""}
                </dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </div>
  );
}

/** Ask about a train in English or Hinglish. The model reads the question; code finds the answer. */
export function ChatPanel() {
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [context, setContext] = useState<ChatContext | null>(null);
  const ask = useAsk();
  const examples = useChatExamples();
  const network = useNetwork();
  const endRef = useRef<HTMLDivElement>(null);

  const stopsByTrain = useMemo(
    () => Object.fromEntries((network.data?.trains ?? []).map((t) => [t.number, t.stops.map((s) => s.station)])),
    [network.data],
  );

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, ask.isPending]);

  const send = (message: string, fresh = false) => {
    const trimmed = message.trim();
    if (!trimmed || ask.isPending) return;
    const id = Date.now();
    setTurns((previous) => [...previous, { id, role: "user", text: trimmed }]);
    setText("");
    ask.mutate(
      { message: trimmed, context: fresh ? null : context },
      {
        onSuccess: (result) => {
          setTurns((previous) => [...previous, { id: id + 1, role: "bot", result }]);
          setContext(result.context);
        },
      },
    );
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    send(text);
  };

  return (
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
      <section className="flex min-h-[560px] min-w-0 flex-col rounded-lg border border-zinc-200 bg-zinc-50/60">
        <div className="flex-1 space-y-4 p-4">
          {turns.length === 0 && (
            <div className="mx-auto max-w-xl space-y-2 py-10 text-center">
              <p className="text-base font-semibold text-zinc-800">Where is my train?</p>
              <p className="text-sm text-zinc-500">
                Ask in English or Hinglish: "22448 ka status kya hai?", "is 13427 late at Patna?", "which stations cause the most
                delay in January?". You get the live position, a p50 to p90 arrival forecast, and how late the train usually is,
                computed from a year of running history.
              </p>
            </div>
          )}
          {turns.map((turn) =>
            turn.role === "user" ? (
              <div key={turn.id} className="flex justify-end">
                <p className="max-w-[80%] rounded-2xl rounded-tr-sm bg-zinc-900 px-4 py-2 text-sm text-white">{turn.text}</p>
              </div>
            ) : (
              <BotTurn
                key={turn.id}
                result={turn.result}
                stopsFor={(number) => stopsByTrain[number] ?? []}
                onOption={(value) => send(value)}
                disabled={ask.isPending}
              />
            ),
          )}
          {ask.isPending && (
            <p className="flex items-center gap-2 text-sm text-zinc-500">
              <Spinner /> Checking the live feed…
            </p>
          )}
          <ErrorText error={ask.error} />
          <div ref={endRef} />
        </div>
        <form onSubmit={onSubmit} className="sticky bottom-0 flex gap-2 border-t border-zinc-200 bg-white p-3">
          <input
            className={inputClass}
            placeholder="e.g. 13427 Patna kab pahunchegi?"
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-label="Message"
          />
          <Button type="submit" variant="primary" disabled={ask.isPending || !text.trim()}>
            Send
          </Button>
        </form>
      </section>

      <aside className="min-w-0 space-y-4 lg:sticky lg:top-5">
        <Panel title="Try these">
          <ul className="space-y-1.5">
            {(examples.data ?? []).map((example) => (
              <li key={example}>
                <button
                  type="button"
                  className="text-left text-sm text-indigo-700 hover:text-indigo-900 disabled:text-zinc-400"
                  disabled={ask.isPending}
                  onClick={() => send(example, true)}
                >
                  {example}
                </button>
              </li>
            ))}
          </ul>
        </Panel>
        <LiveBoard onPick={(number) => send(`Where is ${number}?`, true)} />
      </aside>
    </div>
  );
}
