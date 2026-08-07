import assert from "node:assert/strict";
import test from "node:test";

import { mayGenerate, selectCandidate, updateReview } from "../lib/history-flow-core.mjs";

const pack = { pack_id: "history-comeback-001", human_review: { source_status: "unreviewed", meaning_status: "unreviewed" } };
const candidate = { pack_id: pack.pack_id, title: "One-player reset" };

test("retains the complete selected pack and updates only the requested review state", () => {
  const selected = selectCandidate(candidate, new Map([[pack.pack_id, pack]]));
  assert.equal(selected.kind, "source_review");
  assert.equal(selected.pack, pack);
  const verified = updateReview(selected.pack, { source_status: "verified" });
  assert.deepEqual(verified.human_review, { source_status: "verified", meaning_status: "unreviewed" });
});

test("generation is legal only after source verification and before a meaning decision", () => {
  const sourceReview = { kind: "source_review", pack };
  const meaningReview = { kind: "meaning_review", pack: updateReview(pack, { source_status: "verified" }) };
  const confirmed = { kind: "meaning_review", pack: updateReview(meaningReview.pack, { meaning_status: "confirmed" }) };
  assert.equal(mayGenerate(sourceReview), false);
  assert.equal(mayGenerate(meaningReview), true);
  assert.equal(mayGenerate(confirmed), false);
});

test("missing candidate packs and disputed or dismissed decisions cannot enter generation", () => {
  assert.deepEqual(selectCandidate(candidate, new Map()), { kind: "history_error", message: "The selected match could not be loaded safely." });
  const disputed = { kind: "meaning_review", pack: updateReview(pack, { source_status: "disputed" }) };
  const dismissed = { kind: "meaning_review", pack: updateReview(updateReview(pack, { source_status: "verified" }), { meaning_status: "dismissed" }) };
  assert.equal(mayGenerate(disputed), false);
  assert.equal(mayGenerate(dismissed), false);
});
