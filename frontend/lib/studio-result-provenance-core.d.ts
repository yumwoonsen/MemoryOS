export type StudioResultStatus = "pending_player_decision" | "not_generated" | "rejected";

export function hasStudioModeOriginPair(
  status: StudioResultStatus,
  mode: unknown,
  contentOrigin: unknown,
): boolean;
