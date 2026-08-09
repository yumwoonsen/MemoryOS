export type PlayerRerunnableViewKind = "no_memory" | "error" | "declined";

export function canGenerateAnotherGroundedChapter(viewKind: string): viewKind is PlayerRerunnableViewKind;
