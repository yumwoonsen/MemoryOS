/** Pure Phase 3 reunion helpers. The post-accept gameplay is an explicit static prototype simulation. */

export function buildInvitees(roster) {
  const seen = new Set();
  return roster.flatMap((recipient) => {
    if (
      !recipient
      || typeof recipient.recipient_ref !== "string"
      || typeof recipient.display_name !== "string"
      || !["online", "away"].includes(recipient.activity)
      || typeof recipient.is_current_player !== "boolean"
      || seen.has(recipient.recipient_ref)
    ) {
      return [];
    }
    seen.add(recipient.recipient_ref);
    return [{
      recipient_ref: recipient.recipient_ref,
      display_name: recipient.display_name,
      activity: recipient.activity,
      is_current_player: recipient.is_current_player,
    }];
  });
}

export function areInviteesJoined(invitees, recipients) {
  const responseByRef = new Map(recipients.map((recipient) => [recipient.recipient_ref, recipient.response]));
  return invitees.length > 0
    && invitees.every((invitee) => {
      const response = responseByRef.get(invitee.recipient_ref);
      return response === "self_joined" || response === "joined";
    });
}

export function createPrototypeMatchOutcome(family, invitees, objectives) {
  const currentPlayer = invitees.find((invitee) => invitee.is_current_player);
  const assignedRecipientRef = objectives.find((objective) => objective.assigned_recipient_ref)?.assigned_recipient_ref;
  const roleReversalPlayer = invitees.find((invitee) => invitee.recipient_ref === assignedRecipientRef)
    ?? currentPlayer;
  const completionCopy = family === "role_reversal"
    ? `${roleReversalPlayer?.display_name ?? "The previously saved player"} completed the squad's first revival.`
    : family === "redemption"
      ? "The squad reached the top three."
      : "The full squad completed one match together.";
  return {
    simulation_id: "prototype-match-simulation-001",
    family,
    completion_copy: completionCopy,
    objective_results: objectives
      .filter((objective) => objective.required)
      .map((objective) => ({
        objective_ref: objective.objective_ref,
        description: objective.description,
        completed: true,
      })),
    complete: true,
  };
}

export function createContinuationChapter(memory, nextChapter, outcome) {
  if (!outcome.complete) return null;
  const title = nextChapter.title.split(":").at(-1)?.trim() || nextChapter.title;
  const highlights = outcome.objective_results
    .filter((objective) => objective.completed)
    .map((objective) => objective.description);
  return {
    title,
    summary: `${outcome.completion_copy} In this prototype, the original memory now has a successful sequel.`,
    highlights,
    original_memory_title: memory.title,
  };
}
