import { useState } from "react";

import { ChatPanel } from "./features/chat/ChatPanel";
import { HealthBadge } from "./features/health/HealthBadge";
import { PatternsPage } from "./features/patterns/PatternsPage";

type Tab = "chat" | "patterns";

const TABS: { id: Tab; label: string }[] = [
  { id: "chat", label: "Where is my train?" },
  { id: "patterns", label: "Delay patterns" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>(() =>
    new URLSearchParams(window.location.search).get("tab") === "patterns" ? "patterns" : "chat",
  );

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <img src="/train.svg" alt="" className="h-7 w-7 shrink-0" />
            <div className="min-w-0">
              <h1 className="text-base font-semibold leading-tight">Rail Delay Agent</h1>
              <p className="truncate text-xs text-zinc-500">
                Live running status + a year of history → where and when trains lose time → an answer you can trust
              </p>
            </div>
          </div>
          <HealthBadge />
        </div>
        <nav className="mx-auto flex max-w-[1400px] gap-1 px-4 sm:px-6" aria-label="Views">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                tab === id ? "border-zinc-900 text-zinc-900" : "border-transparent text-zinc-500 hover:text-zinc-800"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-5 sm:px-6">
        {tab === "chat" && <ChatPanel />}
        {tab === "patterns" && <PatternsPage />}
      </main>

      <footer className="border-t border-zinc-200 bg-white px-4 py-3 text-center text-xs text-zinc-500">
        A learning project. Trains, timetables and delays are simulated; station locations are approximate. Not affiliated
        with Indian Railways, IRCTC or NTES.
      </footer>
    </div>
  );
}
