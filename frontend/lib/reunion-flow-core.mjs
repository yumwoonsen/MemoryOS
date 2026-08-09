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
  const assignedRecipientRef = objectives.find(
    (objective) => objective.required && objective.assigned_recipient_ref,
  )?.assigned_recipient_ref;
  const roleReversalPlayer = invitees.find((invitee) => invitee.recipient_ref === assignedRecipientRef)
    ?? currentPlayer;
  const completionCopy = family === "role_reversal"
    ? `${roleReversalPlayer?.display_name ?? "The previously saved player"} completed the squad's first revival.`
    : family === "redemption"
      ? "The squad reached the top three."
      : family === "return_to_place"
        ? "The invited squad returned to the original location together."
        : family === "landing_rendezvous"
          ? "The invited squad landed together at the named drop point."
          : family === "duo_assist"
            ? "The assigned duo combined for one elimination."
            : "The full squad completed one match together.";
  const firstBonusIndex = objectives.findIndex(
    (objective) => objective.objective_role === "bonus",
  );
  const objectiveResults = objectives.map((objective, index) => ({
    objective_ref: objective.objective_ref,
    description: objective.description,
    objective_role: objective.objective_role,
    required: objective.required,
    // The static demo guarantees required rules and scripts at most one bonus success.
    // Bonuses remain optional and never gate completion of the selected Next Chapter.
    completed: objective.required || index === firstBonusIndex,
  }));
  const requiredResults = objectiveResults.filter((objective) => objective.required);
  return {
    simulation_id: "prototype-match-simulation-001",
    family,
    completion_copy: completionCopy,
    objective_results: objectiveResults,
    complete: requiredResults.length > 0
      && requiredResults.every((objective) => objective.completed),
  };
}

const completedChapterTitles = {
  reunion: ["Together Again", "The Squad Reunited"],
  role_reversal: ["The Favour Returned", "Roles Reversed"],
  redemption: ["The Comeback Complete", "The Final Push Landed"],
  return_to_place: ["Back Where It Began", "The Rescue Site Revisited"],
  landing_rendezvous: ["Same Drop, Same Squad", "Touchdown Together"],
  duo_assist: ["The Setup and the Finish", "Two Players, One Finish"],
};

function shortChapterTitle(title) {
  return title.split(":").at(-1)?.trim() || title.trim();
}

function titleKey(title) {
  return shortChapterTitle(title)
    .toLocaleLowerCase("en")
    .replaceAll(/[^a-z0-9]+/g, " ")
    .trim();
}

function completedChapterTitle(family, acceptedMissionTitle) {
  const candidates = completedChapterTitles[family] ?? ["A New Chapter", "The Story Continued"];
  const acceptedKey = titleKey(acceptedMissionTitle);
  return candidates.find((candidate) => titleKey(candidate) !== acceptedKey)
    ?? `${candidates[0]} Complete`;
}

export function createContinuationChapter(memory, nextChapter, outcome) {
  if (!outcome.complete) return null;
  const acceptedMissionTitle = shortChapterTitle(nextChapter.title);
  const title = completedChapterTitle(outcome.family, acceptedMissionTitle);
  const highlights = outcome.objective_results
    .filter((objective) => objective.completed)
    .map((objective) => objective.description);
  return {
    title,
    summary: `${outcome.completion_copy} The squad turned "${memory.title}" into a completed sequel through "${acceptedMissionTitle}".`,
    highlights,
    original_memory_title: memory.title,
  };
}
