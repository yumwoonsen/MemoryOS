import { MemoryExperience } from "./memory-experience";
import { playerExperienceSeed } from "@/lib/player-scenario.server";

export default function Home() {
  return <MemoryExperience seed={playerExperienceSeed()} />;
}
