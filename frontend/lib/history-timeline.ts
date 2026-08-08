import { buildSafeHistoryItems as buildSafeHistoryItemsCore } from "./history-timeline-core.mjs";

export type SafeHistoryItem = {
  game: string;
  mode: string;
  map_name: string;
  played_at: string;
  placement: number | null;
  opted_in_count: number;
  consent_safe_moments: number;
};

export function buildSafeHistoryItems(packs: unknown): SafeHistoryItem[] {
  return buildSafeHistoryItemsCore(packs) as SafeHistoryItem[];
}
