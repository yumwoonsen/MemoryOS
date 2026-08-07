import historicalPacks from "../../../backend/data/historical_memory_packs.json";

import { HistoryExperience } from "./history-experience";
import type { MemoryPackV11 } from "@/lib/history-types";

export default function HistoryPage() {
  const initialPacks = historicalPacks as MemoryPackV11[];
  // The hosted inbox fixture represents telemetry-verified facts before the player decides
  // whether the resurfaced moment is personally relevant.
  const deliveryPacks = initialPacks.map((pack) => pack.human_review.source_status === "verified"
    ? { ...pack, human_review: { ...pack.human_review, meaning_status: "unreviewed" as const } }
    : pack);
  return <HistoryExperience initialPacks={deliveryPacks} />;
}
