// One function per API endpoint. Components never build URLs themselves.

import { request } from "./http";
import type {
  ChatContext,
  ChatResult,
  Health,
  LiveStatus,
  ModelCard,
  Network,
  ReliabilityReport,
  SeasonalityReport,
  StationReport,
  UnusualArrival,
} from "./types";

export const api = {
  health: () => request<Health>("/api/health"),
  network: () => request<Network>("/api/network"),

  chatExamples: () => request<string[]>("/api/chat/examples"),
  ask: (message: string, context: ChatContext | null) =>
    request<ChatResult>("/api/chat", { method: "POST", body: { message, context } }),

  board: () => request<LiveStatus[]>("/api/live/board"),
  unusual: () => request<UnusualArrival[]>("/api/live/unusual"),

  hotspots: (months: number[]) => {
    const search = new URLSearchParams();
    months.forEach((m) => search.append("months", String(m)));
    const text = search.toString();
    return request<StationReport>(`/api/patterns/hotspots${text ? `?${text}` : ""}`);
  },
  seasonality: () => request<SeasonalityReport>("/api/patterns/seasonality"),
  reliability: () => request<ReliabilityReport>("/api/patterns/reliability"),
  model: () => request<ModelCard>("/api/patterns/model"),
};
