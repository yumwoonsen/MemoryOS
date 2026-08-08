import historicalPacks from "../../../backend/data/historical_memory_packs.json";

import { HistoryExperience } from "./history-experience";
import { buildSafeHistoryItems } from "@/lib/history-timeline";
import { CURRENT_MEMORY_MATCH_ID } from "@/lib/player-demo";

export default function HistoryPage() {
  const retainedPacks = historicalPacks.filter(
    (pack) => pack.match.match_id !== CURRENT_MEMORY_MATCH_ID,
  );
  return <HistoryExperience items={buildSafeHistoryItems(retainedPacks)} />;
}
