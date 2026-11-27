// React Query hooks: the only place that knows about cache keys and polling.

import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "../api/endpoints";
import type { ChatContext } from "../api/types";

const LIVE_POLL_MS = 5000;

/** Health polls while the models are still building, then every few seconds for the clock. */
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: (query) => (query.state.data?.analytics.state === "building" ? 1500 : LIVE_POLL_MS),
  });
}

/** True once the analytics are built; pattern queries wait for it. */
export function useReady(): boolean {
  return useHealth().data?.analytics.state === "ready";
}

export function useNetwork() {
  return useQuery({ queryKey: ["network"], queryFn: api.network, staleTime: Infinity });
}

export function useChatExamples() {
  return useQuery({ queryKey: ["chat", "examples"], queryFn: api.chatExamples, staleTime: Infinity });
}

export function useAsk() {
  return useMutation({
    mutationFn: ({ message, context }: { message: string; context: ChatContext | null }) => api.ask(message, context),
  });
}

export function useBoard() {
  return useQuery({ queryKey: ["live", "board"], queryFn: api.board, refetchInterval: LIVE_POLL_MS });
}

export function useUnusual() {
  const ready = useReady();
  return useQuery({ queryKey: ["live", "unusual"], queryFn: api.unusual, enabled: ready, refetchInterval: LIVE_POLL_MS });
}

export function useHotspots(months: number[]) {
  const ready = useReady();
  return useQuery({
    queryKey: ["patterns", "hotspots", months],
    queryFn: () => api.hotspots(months),
    enabled: ready,
    placeholderData: (previous) => previous,
  });
}

export function useSeasonality() {
  const ready = useReady();
  return useQuery({ queryKey: ["patterns", "seasonality"], queryFn: api.seasonality, enabled: ready, staleTime: Infinity });
}

export function useReliability() {
  const ready = useReady();
  return useQuery({ queryKey: ["patterns", "reliability"], queryFn: api.reliability, enabled: ready, staleTime: Infinity });
}

export function useModelCard() {
  const ready = useReady();
  return useQuery({ queryKey: ["patterns", "model"], queryFn: api.model, enabled: ready, staleTime: Infinity });
}
