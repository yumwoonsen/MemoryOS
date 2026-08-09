import { MemoryExperience } from "./memory-experience";
import { playerExperienceSeeds } from "@/lib/player-scenario.server";

export default function Home() {
  return <MemoryExperience seeds={playerExperienceSeeds()} />;
}
