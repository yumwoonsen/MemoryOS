/** Pure, dependency-free review transitions used by the Phase 2B client state machine. */
export function updateReview(pack, review) {
  return { ...pack, human_review: { ...pack.human_review, ...review } };
}

export function selectCandidate(candidate, packs) {
  const pack = packs.get(candidate.pack_id);
  return pack
    ? { kind: "source_review", candidate, pack }
    : { kind: "history_error", message: "The selected match could not be loaded safely." };
}

export function mayGenerate(state) {
  return state.kind === "meaning_review"
    && state.pack.human_review.source_status === "verified"
    && state.pack.human_review.meaning_status === "unreviewed";
}
