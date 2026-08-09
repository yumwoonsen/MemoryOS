export function hasStudioModeOriginPair(status, mode, contentOrigin) {
  if (status === "pending_player_decision") {
    return (mode === "live_ai" && contentOrigin === "live_ai_validated")
      || (mode === "deterministic_demo" && contentOrigin === "deterministic_studio_sample")
      || (mode === "saved_replay" && contentOrigin === "saved_live_replay");
  }
  if (status !== "not_generated" && status !== "rejected") return false;
  return contentOrigin === "no_player_content"
    && (mode === "live_ai" || mode === "deterministic_demo" || mode === "saved_replay");
}
