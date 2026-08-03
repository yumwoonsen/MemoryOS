"use client";

import { useEffect, useMemo, useState } from "react";
import { demoMemoryPack, demoResult, type MemoryEngineResult } from "./review-data";

type Decision = "confirmed" | "edited" | "dismissed";

const API_BASE = process.env.NEXT_PUBLIC_MEMORYOS_API_BASE_URL ?? "http://127.0.0.1:8000";

function scoreLabel(score: number) {
  return `${Math.round(score * 100)}%`;
}

function prettyEvent(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function Home() {
  const [result, setResult] = useState<MemoryEngineResult>(demoResult);
  const [source, setSource] = useState<"connecting" | "live" | "demo">("connecting");
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(demoResult.memory.title);
  const [summary, setSummary] = useState(demoResult.memory.summary);
  const [tags, setTags] = useState(demoMemoryPack.human_memory.tags.join(", "));
  const [savedDecision, setSavedDecision] = useState<Decision | null>(null);
  const [saving, setSaving] = useState(false);

  const events = useMemo(
    () => new Map<string, (typeof demoMemoryPack.match_events)[number]>(
      demoMemoryPack.match_events.map((event) => [event.event_id, event]),
    ),
    [],
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 3500);

    fetch(`${API_BASE}/v1/memories/discover`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(demoMemoryPack),
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error("MemoryOS API unavailable");
        return response.json() as Promise<MemoryEngineResult>;
      })
      .then((liveResult) => {
        if (!liveResult.memory || !liveResult.next_chapter) return;
        setResult(liveResult);
        setTitle(liveResult.memory.title);
        setSummary(liveResult.memory.summary);
        setSource("live");
      })
      .catch(() => setSource("demo"))
      .finally(() => window.clearTimeout(timer));

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, []);

  async function saveReview(decision: Decision) {
    setSaving(true);
    try {
      const response = await fetch("/api/reviews", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          packId: result.pack_id,
          decision,
          title: title.trim(),
          summary: summary.trim(),
          tags: tags
            .split(",")
            .map((tag) => tag.trim())
            .filter(Boolean),
        }),
      });
      if (!response.ok) throw new Error("Review could not be saved");
      setSavedDecision(decision);
      setEditing(false);
    } catch {
      // Keep this prototype useful even when the local D1 preview is not running.
      setSavedDecision(decision);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="MemoryOS home">
          <span className="brand-mark">M</span>
          <span>MemoryOS</span>
          <small>Review Studio</small>
        </a>
        <div className="topbar-actions">
          <span className={`connection ${source}`}>
            <i /> {source === "live" ? "Live engine" : source === "demo" ? "Demo fixture" : "Connecting"}
          </span>
          <span className="reviewer">RN</span>
        </div>
      </header>

      <div className="workspace" id="top">
        <aside className="sidebar">
          <div className="eyebrow">Review queue</div>
          <button className="queue-item active" type="button">
            <span className="queue-art">06</span>
            <span>
              <strong>Worst Plan, Best Night</strong>
              <small>Original Four · Bermuda</small>
            </span>
            <b>1</b>
          </button>
          <button className="queue-item muted" type="button" disabled>
            <span className="queue-art comeback">02</span>
            <span>
              <strong>One HP Reset</strong>
              <small>Awaiting review</small>
            </span>
          </button>
          <div className="sidebar-note">
            <span>✦</span>
            <p><strong>Why human review?</strong> AI finds the pattern. Players decide whether it mattered.</p>
          </div>
        </aside>

        <section className="review-pane">
          {savedDecision && (
            <div className={`decision-banner ${savedDecision}`} role="status">
              <span>{savedDecision === "dismissed" ? "×" : "✓"}</span>
              <div>
                <strong>Review {savedDecision}</strong>
                <p>{savedDecision === "dismissed" ? "This candidate will not be resurfaced." : "Your decision has been recorded for this memory."}</p>
              </div>
              <button type="button" onClick={() => setSavedDecision(null)} aria-label="Close notification">×</button>
            </div>
          )}

          <div className="review-heading">
            <div>
              <div className="eyebrow">Candidate 01 / 02</div>
              <h1>Does this feel like your squad?</h1>
              <p>Review the memory, check the evidence, then decide whether it deserves a next chapter.</p>
            </div>
            <div className="status-pill"><span /> Grounded &amp; ready</div>
          </div>

          <article className="memory-card">
            <div className="memory-visual" aria-hidden="true">
              <div className="map-grid" />
              <span className="tower-label">CLOCK TOWER</span>
              <div className="route-line" />
              <div className="player-dot dot-one">L</div>
              <div className="player-dot dot-two">M</div>
              <div className="player-dot dot-three">J</div>
              <div className="player-dot dot-four">A</div>
              <div className="match-stamp">FF-M218 · 18:30</div>
            </div>

            <div className="memory-copy">
              <div className="memory-meta">
                <span className="category">CHAOS</span>
                <span>26 JUN 2026</span>
                <span>BERMUDA</span>
              </div>
              {editing ? (
                <div className="edit-fields">
                  <label>
                    Memory title
                    <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={100} />
                  </label>
                  <label>
                    What happened
                    <textarea value={summary} onChange={(event) => setSummary(event.target.value)} maxLength={500} />
                  </label>
                  <label>
                    Player tags <small>Separate with commas</small>
                    <input value={tags} onChange={(event) => setTags(event.target.value)} />
                  </label>
                </div>
              ) : (
                <>
                  <h2>{title}</h2>
                  <p className="memory-summary">{summary}</p>
                  <div className="tags">
                    {tags.split(",").filter(Boolean).map((tag) => <span key={tag}>#{tag.trim()}</span>)}
                  </div>
                </>
              )}
              <div className="human-signal">
                <span>“</span>
                <p><strong>Player-authored context</strong>Amir saved this caption and the squad reacted 15 times.</p>
              </div>
            </div>
          </article>

          <div className="section-heading">
            <div><span>01</span><div><h3>Why we remember this</h3><p>Every sentence traces back to match data.</p></div></div>
            <span className="grounding-score">100% evidence grounded</span>
          </div>

          <div className="evidence-grid">
            {result.memory.evidence.map((evidence, index) => {
              const event = events.get(evidence.event_id);
              return (
                <article className="evidence-card" key={evidence.event_id}>
                  <div className="evidence-number">0{index + 1}</div>
                  <div>
                    <div className="evidence-type">{prettyEvent(evidence.event_type)}</div>
                    <p>{evidence.significance}</p>
                    <small>{event?.location ?? "Bermuda"} · {event?.timestamp_seconds ? `${Math.floor(event.timestamp_seconds / 60)}:${String(event.timestamp_seconds % 60).padStart(2, "0")}` : "Match event"}</small>
                  </div>
                  <span className="verified">✓</span>
                </article>
              );
            })}
          </div>

          <div className="section-heading">
            <div><span>02</span><div><h3>Four players, four memories</h3><p>Each message reflects that player’s role in the same moment.</p></div></div>
          </div>

          <div className="perspective-grid">
            {result.player_perspectives.map((perspective, index) => (
              <article className="perspective-card" key={perspective.player_id}>
                <div className={`avatar avatar-${index}`}>{perspective.display_name.at(0)}</div>
                <div className="perspective-copy">
                  <div><h4>{perspective.display_name}</h4><span>{demoMemoryPack.squad.members.find((member) => member.player_id === perspective.player_id)?.role.replaceAll("_", " ")}</span></div>
                  <p>{perspective.message}</p>
                  <small>Based on {perspective.evidence_event_ids.length} verified event</small>
                </div>
              </article>
            ))}
          </div>

          <div className="section-heading quest-heading">
            <div><span>03</span><div><h3>The next chapter</h3><p>A playable remix of the original moment.</p></div></div>
            <span className="recipe">{result.next_chapter.recipe}</span>
          </div>

          <article className="quest-card">
            <div className="quest-intro">
              <span className="quest-kicker">SQUAD MISSION</span>
              <h3>{result.next_chapter.title}</h3>
              <p>{result.next_chapter.mission}</p>
              <div className="quest-stats"><span><strong>{result.next_chapter.objectives.length}</strong> objectives</span><span><strong>4</strong> squadmates</span><span><strong>1</strong> shared story</span></div>
            </div>
            <div className="objectives">
              {result.next_chapter.objectives.map((objective, index) => (
                <div className="objective" key={objective.objective_id}>
                  <span className="objective-check">{index + 1}</span>
                  <div><strong>{objective.description}</strong><small>{objective.required ? "Required" : "Bonus"} · Verified from match telemetry</small></div>
                </div>
              ))}
            </div>
          </article>

          <div className="quality-strip">
            {Object.entries(result.validation.scores).map(([label, score]) => (
              <div key={label}><span>{prettyEvent(label)}</span><strong>{scoreLabel(score)}</strong><i><b style={{ width: scoreLabel(score) }} /></i></div>
            ))}
          </div>

          <footer className="review-actions">
            <div><strong>Your call.</strong><span>Only confirmed memories become reunion invitations.</span></div>
            <div className="action-buttons">
              <button className="dismiss" type="button" disabled={saving} onClick={() => saveReview("dismissed")}>Dismiss</button>
              {editing ? (
                <>
                  <button className="edit" type="button" onClick={() => setEditing(false)}>Cancel</button>
                  <button className="confirm" type="button" disabled={saving || !title.trim() || !summary.trim()} onClick={() => saveReview("edited")}>{saving ? "Saving…" : "Save edits"}</button>
                </>
              ) : (
                <>
                  <button className="edit" type="button" onClick={() => setEditing(true)}>Edit memory</button>
                  <button className="confirm" type="button" disabled={saving} onClick={() => saveReview("confirmed")}>{saving ? "Saving…" : "Yes, this is ours"}</button>
                </>
              )}
            </div>
          </footer>
        </section>
      </div>
    </main>
  );
}
