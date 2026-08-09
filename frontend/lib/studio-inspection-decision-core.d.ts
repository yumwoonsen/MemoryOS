export type StudioInspectionDecision = "accepted";
export type StudioResultTab = "summary" | "mission";
export type StudioContentOrigin = "live_ai_validated" | "no_player_content" | "saved_live_replay";

export function studioInspectionDecision(
  contentOrigin: StudioContentOrigin | null,
  resultStatus: "pending_player_decision" | "not_generated" | "rejected" | null,
): StudioInspectionDecision | null;

export function studioInitialResultTab(
  contentOrigin: StudioContentOrigin,
  resultStatus: "pending_player_decision" | "not_generated" | "rejected",
): StudioResultTab;
