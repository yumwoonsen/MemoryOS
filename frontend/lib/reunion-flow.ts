import type { MissionFamilyV2 } from "@/lib/ai-memory-contract";
import type {
  PlayerPendingDeliveryProjectionV2,
  PlayerRosterMemberV2,
} from "@/lib/player-delivery";
import {
  areInviteesJoined as coreAreInviteesJoined,
  buildInvitees as coreBuildInvitees,
  createContinuationChapter as coreCreateContinuationChapter,
  createPrototypeMatchOutcome as coreCreatePrototypeMatchOutcome,
} from "./reunion-flow-core.mjs";

export type Invitee = {
  recipient_ref: string;
  display_name: string;
  activity: "online" | "away";
  is_current_player: boolean;
};

export type InvitationResponse = {
  recipient_ref: string;
  response: "self_joined" | "pending" | "joined";
};

export type PrototypeObjectiveOutcome = {
  objective_ref: string;
  description: string;
  objective_role: PlayerPendingDeliveryProjectionV2["next_chapter"]["objectives"][number]["objective_role"];
  required: boolean;
  completed: boolean;
};

export type PrototypeMatchOutcome = {
  simulation_id: string;
  family: MissionFamilyV2;
  completion_copy: string;
  objective_results: PrototypeObjectiveOutcome[];
  complete: boolean;
};

export type ContinuationChapter = {
  title: string;
  summary: string;
  highlights: string[];
  original_memory_title: string;
};

export function areInviteesJoined(invitees: Invitee[], recipients: InvitationResponse[]) {
  return coreAreInviteesJoined(invitees, recipients) as boolean;
}

export function buildInvitees(roster: PlayerRosterMemberV2[]): Invitee[] {
  return coreBuildInvitees(roster) as Invitee[];
}

export function createPrototypeMatchOutcome(
  family: MissionFamilyV2,
  invitees: Invitee[],
  objectives: PlayerPendingDeliveryProjectionV2["next_chapter"]["objectives"],
): PrototypeMatchOutcome {
  return coreCreatePrototypeMatchOutcome(family, invitees, objectives) as PrototypeMatchOutcome;
}

export function createContinuationChapter(
  memory: PlayerPendingDeliveryProjectionV2["memory"],
  nextChapter: PlayerPendingDeliveryProjectionV2["next_chapter"],
  outcome: PrototypeMatchOutcome,
): ContinuationChapter | null {
  return coreCreateContinuationChapter(memory, nextChapter, outcome) as ContinuationChapter | null;
}
