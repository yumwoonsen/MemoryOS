export function buildSafeHistoryItems(packs) {
  const seenMatchIds = new Set();
  const items = [];

  for (const pack of Array.isArray(packs) ? packs : []) {
    if (
      !pack
      || pack.schema_version !== "1.1"
      || pack.human_review?.source_status !== "verified"
      || pack.human_review?.meaning_status !== "confirmed"
      || typeof pack.pack_id !== "string"
      || typeof pack.match?.match_id !== "string"
      || seenMatchIds.has(pack.match.match_id)
      || typeof pack.match?.mode !== "string"
      || typeof pack.match?.map_name !== "string"
      || typeof pack.match?.played_at !== "string"
      || !Array.isArray(pack.squad?.members)
      || !Array.isArray(pack.match_events)
    ) {
      continue;
    }

    const target = pack.squad.members.find(
      (member) => member?.player_id === pack.player_profile?.player_id,
    );
    const optedInMembers = pack.squad.members.filter((member) => member?.opted_in === true);
    const optedInCount = optedInMembers.length;
    if (target?.opted_in !== true || optedInCount < 2) continue;

    const optedInIds = new Set(optedInMembers.map((member) => member.player_id));
    const consentSafeMoments = pack.match_events.filter((event) => (
      typeof event?.actor_id === "string"
      && optedInIds.has(event.actor_id)
      && (event.target_id == null || optedInIds.has(event.target_id))
    )).length;

    seenMatchIds.add(pack.match.match_id);
    items.push({
      game: "Free Fire",
      mode: pack.match.mode,
      map_name: pack.match.map_name,
      played_at: pack.match.played_at,
      placement: Number.isInteger(pack.match.placement) ? pack.match.placement : null,
      opted_in_count: optedInCount,
      consent_safe_moments: consentSafeMoments,
    });
  }

  return items.sort((left, right) => right.played_at.localeCompare(left.played_at));
}
