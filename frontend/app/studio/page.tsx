import type { Metadata } from "next";
import { StudioDashboard } from "./studio-dashboard";

export const metadata: Metadata = {
  title: "MemoryOS Studio",
  description: "Inspect the evidence, model boundary, structured outputs, and validation behind MemoryOS.",
  robots: { index: false, follow: false },
};

export default function StudioPage() {
  return <StudioDashboard />;
}
