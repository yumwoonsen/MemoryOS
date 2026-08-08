export function isDeliveryBoundToPackCore(delivery, pack) {
  if (
    !delivery
    || !pack
    || delivery.pack_id !== pack.pack_id
    || !Array.isArray(pack.squad?.members)
    || !Array.isArray(pack.match_events)
    || !Array.isArray(delivery.player_perspectives)
    || !Array.isArray(delivery.memory?.evidence)
    || !Array.isArray(delivery.next_chapter?.objectives)
  ) {
    return false;
  }

  const optedInMembers = pack.squad.members.filter((member) => member?.opted_in === true);
  const optedInById = new Map(optedInMembers.map((member) => [member.player_id, member]));
  const eventIds = new Set(pack.match_events.map((event) => event?.event_id));
  const currentPlayer = optedInById.get(pack.player_profile?.player_id);
  if (!currentPlayer || delivery.player_perspectives.length !== optedInMembers.length) return false;

  const seenPerspectiveIds = new Set();
  const perspectivesMatchRoster = delivery.player_perspectives.every((perspective) => {
    const member = optedInById.get(perspective?.player_id);
    if (
      !member
      || seenPerspectiveIds.has(perspective.player_id)
      || member.display_name !== perspective.display_name
      || !Array.isArray(perspective.evidence_event_ids)
      || !perspective.evidence_event_ids.every((eventId) => eventIds.has(eventId))
    ) {
      return false;
    }
    seenPerspectiveIds.add(perspective.player_id);
    return true;
  });
  if (!perspectivesMatchRoster) return false;

  const memoryEvidenceIsBound = delivery.memory.evidence.every(
    (evidence) => eventIds.has(evidence?.event_id),
  );
  const missionIsBound = delivery.next_chapter.objectives.every((objective) => (
    objective
    && (objective.assigned_player_id == null || optedInById.has(objective.assigned_player_id))
    && Array.isArray(objective.source_event_ids)
    && objective.source_event_ids.every((eventId) => eventIds.has(eventId))
  ));
  return memoryEvidenceIsBound && missionIsBound;
}
