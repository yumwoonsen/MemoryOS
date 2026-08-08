import type {
  MissionObjectiveV2,
  PlayerPendingDeliveryV2,
  PlayerPerspectiveV2,
} from "@/lib/ai-memory-contract";
import {
  buildInvitees as coreBuildInvitees,
  createContinuationChapter as coreCreateContinuationChapter,
  createSyntheticRematch as coreCreateSyntheticRematch,
  verifyMission as coreVerifyMission,
} from "./reunion-flow-core.mjs";

export type Invitee = {
  player_id: string;
  display_name: string;
  is_current_player: boolean;
};

export type SyntheticMatchResult = {
  schema_version: "1.0";
  match_id: string;
  label: string;
  metrics: Record<string, string | number | boolean | string[]>;
};

export type ObjectiveResult = {
  objective_id: string;
  description: string;
  required: boolean;
  passed: boolean;
};

export type MissionVerification = {
  match_id: string;
  label: string;
  objective_results: ObjectiveResult[];
  required_passed: number;
  required_total: number;
  complete: boolean;
};

export type ContinuationChapter = {
  title: string;
  summary: string;
  highlights: string[];
  original_memory_title: string;
};

export function buildInvitees(
  perspectives: PlayerPerspectiveV2[],
  currentPlayerId?: string,
): Invitee[] {
  return coreBuildInvitees(perspectives, currentPlayerId) as Invitee[];
}

export function createSyntheticRematch(invitees: Invitee[]): SyntheticMatchResult {
  return coreCreateSyntheticRematch(invitees) as SyntheticMatchResult;
}

export function verifyMission(
  objectives: MissionObjectiveV2[],
  matchResult: SyntheticMatchResult,
): MissionVerification {
  return coreVerifyMission(objectives, matchResult) as MissionVerification;
}

export function createContinuationChapter(
  memory: PlayerPendingDeliveryV2["memory"],
  nextChapter: PlayerPendingDeliveryV2["next_chapter"],
  verification: MissionVerification,
): ContinuationChapter | null {
  return coreCreateContinuationChapter(memory, nextChapter, verification) as ContinuationChapter | null;
}
