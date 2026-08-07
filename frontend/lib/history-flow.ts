import type {
  HistoricalCandidate,
  HistoricalDiscoveryResponse,
  MemoryPackV11,
  ReadyMemoryResult,
} from "@/lib/history-types";
import {
  mayGenerate as coreMayGenerate,
  selectCandidate as coreSelectCandidate,
  updateReview as coreUpdateReview,
} from "./history-flow-core.mjs";

export type HistoryState =
  | { kind: "history_idle" }
  | { kind: "history_loading" }
  | { kind: "history_error"; message: string }
  | { kind: "candidates_ready"; discovery: HistoricalDiscoveryResponse }
  | { kind: "source_review"; candidate: HistoricalCandidate; pack: MemoryPackV11 }
  | { kind: "source_disputed" }
  | { kind: "meaning_review"; candidate: HistoricalCandidate; pack: MemoryPackV11 }
  | { kind: "meaning_dismissed" }
  | { kind: "generation_loading"; candidate: HistoricalCandidate; pack: MemoryPackV11 }
  | { kind: "generation_error"; candidate: HistoricalCandidate; pack: MemoryPackV11; message: string }
  | { kind: "ready"; result: ReadyMemoryResult; pack: MemoryPackV11 }
  | { kind: "rejected"; message: string };

export function updateReview(
  pack: MemoryPackV11,
  review: Partial<MemoryPackV11["human_review"]>,
): MemoryPackV11 {
  return coreUpdateReview(pack, review) as MemoryPackV11;
}

export function selectCandidate(
  candidate: HistoricalCandidate,
  packs: Map<string, MemoryPackV11>,
): HistoryState {
  return coreSelectCandidate(candidate, packs) as HistoryState;
}

export function mayGenerate(state: HistoryState): state is Extract<HistoryState, { kind: "meaning_review" }> {
  return coreMayGenerate(state);
}
