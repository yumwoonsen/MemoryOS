import comebackMemory from "@/data/comeback_memory.json";
import funnyMemory from "@/data/funny_memory.json";
import insufficientMemory from "@/data/insufficient_memory.json";

import type { MemoryPack, Scenario, ScenarioKey } from "./types";

export const scenarios: Scenario[] = [
  {
    key: "ready",
    label: "Ready to continue",
    title: "Worst Plan, Best Night",
    subtitle: "Bermuda · Original Four · 37 days apart",
    pack: funnyMemory as MemoryPack,
  },
  {
    key: "review",
    label: "Needs your call",
    title: "One HP Reset",
    subtitle: "Kalahari · After-School Squad · 18 days apart",
    pack: comebackMemory as MemoryPack,
  },
  {
    key: "skipped",
    label: "Safely skipped",
    title: "Match FF-M999",
    subtitle: "Bermuda · 1 low-signal event",
    pack: insufficientMemory as MemoryPack,
  },
];

export const scenarioByKey = Object.fromEntries(
  scenarios.map((scenario) => [scenario.key, scenario]),
) as Record<ScenarioKey, Scenario>;

export const roleLabels: Record<string, string> = {
  aggressive_entry: "Entry",
  support_rescuer: "Rescuer",
  driver: "Driver",
  caller: "Caller",
  flex: "Flex",
  scout: "Scout",
  support: "Support",
  anchor: "Anchor",
};
