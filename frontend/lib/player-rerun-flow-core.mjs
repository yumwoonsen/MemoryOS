const rerunnablePlayerStates = new Set(["no_memory", "error", "declined"]);

export function canGenerateAnotherGroundedChapter(viewKind) {
  return rerunnablePlayerStates.has(viewKind);
}
