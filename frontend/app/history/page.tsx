import historicalPacks from "../../../backend/data/historical_memory_packs.json";

import { HistoryExperience } from "./history-experience";
import type { MemoryPackV11 } from "@/lib/history-types";

export default function HistoryPage() {
  return <HistoryExperience initialPacks={historicalPacks as MemoryPackV11[]} />;
}
