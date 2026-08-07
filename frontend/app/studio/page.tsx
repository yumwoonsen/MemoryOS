import type { Metadata } from "next";
import funnyMemory from "@/data/funny_memory.json";
import type { MemoryPack } from "@/lib/types";
import { StudioDashboard } from "./studio-dashboard";

export const metadata: Metadata = {
  title: "MemoryOS Studio",
  description: "Inspect the evidence, model boundary, structured outputs, and validation behind MemoryOS.",
  robots: { index: false, follow: false },
};

export default function StudioPage() {
  const initialPack = funnyMemory as unknown as MemoryPack;
  return <StudioDashboard initialPack={initialPack} />;
}
