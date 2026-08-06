import { MemoryExperience } from "./memory-experience";
import funnyMemory from "@/data/funny_memory.json";
import type { MemoryPack } from "@/lib/types";

export default function Home() {
  const initialPack = funnyMemory as unknown as MemoryPack;
  return <MemoryExperience initialPack={initialPack} />;
}
