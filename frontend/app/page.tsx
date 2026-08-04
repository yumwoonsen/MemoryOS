"use client";

import { useMemo, useState } from "react";
import { demoMemoryPack, demoResult, type MemoryEngineResult, type MemoryPack } from "./review-data";

type Decision = "confirmed" | "edited" | "dismissed";
type StageName = "discovery" | "perspectives" | "quest" | "validation";
type StageStatus = "idle" | "working" | "complete" | "failed";

interface StageState { stage: StageName; status: StageStatus; message: string }
interface StreamEvent {
  type: "stage" | "result" | "error";
  stage?: StageName;
  status?: StageStatus;
  message?: string;
  result?: MemoryEngineResult;
}

const stageDefaults: StageState[] = [
  { stage: "discovery", status: "idle", message: "Waiting for your match notes" },
  { stage: "perspectives", status: "idle", message: "One grounded recall per player" },
  { stage: "quest", status: "idle", message: "A playable remix of the memory" },
  { stage: "validation", status: "idle", message: "Evidence and safety checks" },
];
const roleDefaults = ["aggressive_entry", "support_rescuer", "driver", "caller", "scout", "anchor"];
const configuredLocalApi = process.env.NEXT_PUBLIC_MEMORYOS_API_BASE_URL?.replace(/\/$/, "");
const localApiBase = configuredLocalApi ?? (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : "");

function cloneDemoPack(): MemoryPack {
  return JSON.parse(JSON.stringify(demoMemoryPack)) as MemoryPack;
}

function scoreLabel(score: number) { return `${Math.round(score * 100)}%`; }
function prettyEvent(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function slugify(value: string, index: number) {
  const slug = value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return slug || `player-${index + 1}`;
}
function inferEventType(note: string) {
  const normalized = note.toLowerCase();
  if (normalized.includes("reviv")) return "revive";
  if (normalized.includes("drove") || normalized.includes("drive") || normalized.includes("escape")) return "vehicle_escape";
  if (normalized.includes("retreat") || normalized.includes("rotate") || normalized.includes("called")) return "retreat_ping";
  if (normalized.includes("surviv") || normalized.includes("final") || normalized.includes("clutch")) return "final_zone_survival";
  return "player_recorded_event";
}
function formatMatchTime(seconds?: number) {
  if (seconds === undefined) return "Match event";
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export default function Home() {
  const [result, setResult] = useState<MemoryEngineResult>(demoResult);
  const [activePack, setActivePack] = useState<MemoryPack>(cloneDemoPack);
  const [source, setSource] = useState<"live" | "demo">("demo");
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(demoResult.memory.title);
  const [summary, setSummary] = useState(demoResult.memory.summary);
  const [tags, setTags] = useState(demoMemoryPack.human_memory.tags.join(", "));
  const [savedDecision, setSavedDecision] = useState<Decision | null>(null);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [stages, setStages] = useState<StageState[]>(stageDefaults);

  const [caption, setCaption] = useState<string>(demoMemoryPack.human_memory.caption);
  const [memberNames, setMemberNames] = useState(demoMemoryPack.squad.members.map((member) => member.display_name).join(", "));
  const [mapName, setMapName] = useState<string>(demoMemoryPack.match.map_name);
  const [location, setLocation] = useState<string>(demoMemoryPack.match_events[0].location);
  const [eventNotes, setEventNotes] = useState([
    "Amir called for retreat three times as the zone closed.",
    "Mei revived Lee at Clock Tower while the zone was closing.",
    "Jo drove all three teammates out with critical health.",
    "Lee and the full squad survived into the final zone.",
  ].join("\n"));
  const [labTags, setLabTags] = useState(demoMemoryPack.human_memory.tags.join(", "));
  const [confirmed, setConfirmed] = useState(true);

  const events = useMemo(() => new Map(activePack.match_events.map((event) => [event.event_id, event])), [activePack]);

  function buildPack(): MemoryPack {
    const names = memberNames.split(",").map((name) => name.trim()).filter(Boolean).slice(0, 6);
    const notes = eventNotes.split("\n").map((note) => note.trim()).filter(Boolean).slice(0, 12);
    if (names.length < 2) throw new Error("Add at least two squad members, separated by commas.");
    if (!notes.length) throw new Error("Add at least one verified match event.");

    const usedIds = new Set<string>();
    const members = names.map((displayName, index) => {
      let playerId = slugify(displayName, index);
      while (usedIds.has(playerId)) playerId = `${playerId}-${index + 1}`;
      usedIds.add(playerId);
      return { player_id: playerId, display_name: displayName, role: roleDefaults[index], opted_in: true };
    });
    const packId = `memory-pack-live-${Date.now()}`;

    return {
      schema_version: "1.0",
      pack_id: packId,
      player_profile: { player_id: members[0].player_id, preferred_role: members[0].role },
      squad: { squad_id: `squad-${packId}`, members, matches_together: 1, days_since_full_squad: 0 },
      match: {
        match_id: `match-${Date.now()}`,
        mode: "battle_royale",
        map_name: mapName.trim() || "Unknown map",
        placement: 1,
        played_at: new Date().toISOString(),
      },
      match_events: notes.map((note, index) => {
        const normalized = note.toLowerCase();
        const eventType = inferEventType(note);
        const actor = members.find((member) => normalized.includes(member.display_name.toLowerCase()));
        const mentionedPlayers = members.filter((member) => normalized.includes(member.display_name.toLowerCase()));
        const target = eventType === "revive"
          ? mentionedPlayers.find((member) => member.player_id !== actor?.player_id)
          : undefined;
        const details: Record<string, string | number | boolean> = { description: note };
        if (eventType === "vehicle_escape") details.passengers = Math.max(members.length - 1, 1);
        if (eventType === "retreat_ping") details.count = Number(normalized.match(/\b\d+\b/)?.[0] ?? 1);
        return {
          event_id: `evt-live-${index + 1}`,
          type: eventType,
          ...(actor ? { actor_id: actor.player_id } : {}),
          ...(target ? { target_id: target.player_id } : {}),
          timestamp_seconds: 600 + index * 30,
          location: location.trim() || mapName.trim() || "Unknown location",
          importance: normalized.includes("reviv") || normalized.includes("surviv") || normalized.includes("escape") ? "high" : "medium",
          details,
        };
      }),
      human_memory: {
        caption: caption.trim() || "Untitled squad memory",
        tags: labTags.split(",").map((tag) => tag.trim()).filter(Boolean),
        author_player_id: members[0].player_id,
        confirmed,
      },
      reactions: { laugh_count: 0, fire_count: 0, saved: true },
      current_context: {
        active_member_ids: members.map((member) => member.player_id),
        resurfacing_reason: "The player asked MemoryOS to turn these verified events into a memory.",
        original_mode_available: true,
      },
    };
  }

  function updateStage(incoming: StreamEvent) {
    if (!incoming.stage || !incoming.status) return;
    setStages((current) => current.map((item) => item.stage === incoming.stage
      ? { ...item, status: incoming.status ?? item.status, message: incoming.message ?? item.message }
      : item));
  }

  async function runLiveMemory() {
    setGenerationError(null);
    setSavedDecision(null);
    setStages(stageDefaults.map((stage) => ({ ...stage })));
    setGenerating(true);
    try {
      const pack = buildPack();
      const generationUrl = localApiBase
        ? `${localApiBase}/v1/memories/generate-stream`
        : "/api/generate-memory";
      const response = await fetch(generationUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pack),
      });
      if (!response.ok || !response.body) throw new Error("The live memory stream could not start.");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let liveResult: MemoryEngineResult | null = null;
      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line) as StreamEvent;
          if (event.type === "stage") updateStage(event);
          if (event.type === "error") throw new Error(event.message ?? "Live memory generation failed.");
          if (event.type === "result" && event.result) liveResult = event.result;
        }
        if (done) break;
      }

      if (!liveResult) throw new Error("The AI finished without returning a reviewable memory.");
      setActivePack(pack);
      setResult(liveResult);
      setTitle(liveResult.memory.title);
      setSummary(liveResult.memory.summary);
      setTags(pack.human_memory.tags.join(", "));
      setSource("live");
      window.setTimeout(() => document.getElementById("review-result")?.scrollIntoView({ behavior: "smooth", block: "start" }), 120);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Live memory generation failed.";
      setGenerationError(message);
      setStages((current) => current.map((stage) => stage.status === "working"
        ? { ...stage, status: "failed", message }
        : stage));
    } finally {
      setGenerating(false);
    }
  }

  function resetGoldenMatch() {
    const pack = cloneDemoPack();
    setActivePack(pack);
    setResult(demoResult);
    setTitle(demoResult.memory.title);
    setSummary(demoResult.memory.summary);
    setTags(pack.human_memory.tags.join(", "));
    setSource("demo");
    setStages(stageDefaults.map((stage) => ({ ...stage })));
    setGenerationError(null);
    setSavedDecision(null);
  }

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
          tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
        }),
      });
      if (!response.ok) throw new Error("Review could not be saved");
      setSavedDecision(decision);
      setEditing(false);
    } catch {
      setSavedDecision(decision);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  const playedAt = new Date(activePack.match.played_at);
  const author = activePack.squad.members.find((member) => member.player_id === activePack.human_memory.author_player_id);

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="MemoryOS home"><span className="brand-mark">M</span><span>MemoryOS</span><small>Review Studio</small></a>
        <div className="topbar-actions"><span className={`connection ${source}`}><i /> {generating ? (localApiBase ? "Local engine working" : "AI working") : source === "live" ? (localApiBase ? "Local result" : "Live AI result") : "Golden match"}</span><span className="reviewer">RN</span></div>
      </header>

      <div className="workspace" id="top">
        <aside className="sidebar">
          <div className="eyebrow">Review queue</div>
          <button className="queue-item active" type="button" onClick={() => document.getElementById("review-result")?.scrollIntoView({ behavior: "smooth" })}>
            <span className="queue-art">{String(activePack.match.placement).padStart(2, "0")}</span>
            <span><strong>{title}</strong><small>{activePack.squad.members.length} players / {activePack.match.map_name}</small></span><b>1</b>
          </button>
          <button className="queue-item muted" type="button" disabled><span className="queue-art comeback">AI</span><span><strong>Next memory</strong><small>Awaiting match notes</small></span></button>
          <div className="sidebar-note"><span aria-hidden="true">+</span><p><strong>Why human review?</strong> AI finds the pattern. Players decide whether it mattered.</p></div>
        </aside>

        <section className="review-pane">
          <section className="memory-lab" aria-labelledby="lab-title">
            <div className="lab-intro">
              <div><div className="eyebrow">Live Memory Lab</div><h1 id="lab-title">Watch the AI build a memory.</h1><p>Give it grounded match notes. MemoryOS will discover the story, personalize it for the squad, create a next chapter, and show each step as it happens.</p></div>
              <span className="model-chip">{localApiBase ? "On-device / no key" : "OpenAI / live"}</span>
            </div>
            <div className="lab-grid">
              <form className="lab-form" onSubmit={(event) => { event.preventDefault(); void runLiveMemory(); }}>
                <label className="wide">Your caption <input value={caption} onChange={(event) => setCaption(event.target.value)} maxLength={120} /></label>
                <label className="wide">Squad names <small>Comma-separated, 2-6 players</small><input value={memberNames} onChange={(event) => setMemberNames(event.target.value)} /></label>
                <label>Map <input value={mapName} onChange={(event) => setMapName(event.target.value)} /></label>
                <label>Location <input value={location} onChange={(event) => setLocation(event.target.value)} /></label>
                <label className="wide">Verified events <small>One factual event per line</small><textarea value={eventNotes} onChange={(event) => setEventNotes(event.target.value)} rows={6} /></label>
                <label className="wide">Tags <small>Comma-separated</small><input value={labTags} onChange={(event) => setLabTags(event.target.value)} /></label>
                <label className="confirmation wide"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span>I confirm these notes describe a real match.</span></label>
                <div className="lab-buttons wide"><button className="run-button" type="submit" disabled={generating}>{generating ? "Making the memory..." : localApiBase ? "Make this memory locally" : "Make this memory live"}</button><button className="reset-button" type="button" onClick={resetGoldenMatch} disabled={generating}>Reset golden match</button></div>
              </form>

              <div className="stage-panel" aria-live="polite" aria-busy={generating}>
                <div className="stage-panel-title"><span>AI activity</span><b>{generationError ? "STOPPED" : generating ? "RUNNING" : source === "live" ? "COMPLETE" : "READY"}</b></div>
                <ol className="stage-timeline">
                  {stages.map((stage, index) => <li className={`stage-card ${stage.status}`} key={stage.stage}><span className="stage-index">{stage.status === "complete" ? "OK" : String(index + 1).padStart(2, "0")}</span><div><strong>{prettyEvent(stage.stage)}</strong><p>{stage.message}</p></div><i aria-hidden="true" /></li>)}
                </ol>
                {generationError && <div className="generation-error" role="alert"><strong>The run stopped.</strong><span>{generationError}</span></div>}
                <p className="privacy-note">{localApiBase ? "Local mode: your match notes stay on this computer. No API key required." : "Your API key stays on the server. Only the match pack is sent to the model."}</p>
              </div>
            </div>
          </section>

          <div id="review-result" className="result-anchor" />
          {savedDecision && <div className={`decision-banner ${savedDecision}`} role="status"><span>{savedDecision === "dismissed" ? "x" : "OK"}</span><div><strong>Review {savedDecision}</strong><p>{savedDecision === "dismissed" ? "This candidate will not be resurfaced." : "Your decision has been recorded for this memory."}</p></div><button type="button" onClick={() => setSavedDecision(null)} aria-label="Close notification">x</button></div>}

          <div className="review-heading">
            <div><div className="eyebrow">Generated candidate</div><h1>Does this feel like your squad?</h1><p>Review the memory, check the evidence, then decide whether it deserves a next chapter.</p></div>
            <div className={`status-pill ${result.validation.passed ? "" : "warning"}`}><span /> {result.validation.passed ? "Grounded & ready" : "Needs attention"}</div>
          </div>

          <article className="memory-card">
            <div className="memory-visual" aria-hidden="true"><div className="map-grid" /><span className="tower-label">{activePack.match_events[0]?.location ?? activePack.match.map_name}</span><div className="route-line" />{activePack.squad.members.slice(0, 4).map((member, index) => <div className={`player-dot dot-${index + 1}`} key={member.player_id}>{member.display_name.at(0)}</div>)}<div className="match-stamp">{activePack.match.match_id} / {formatMatchTime(activePack.match_events.at(-1)?.timestamp_seconds)}</div></div>
            <div className="memory-copy">
              <div className="memory-meta"><span className="category">{result.memory.memory_type}</span><span>{playedAt.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}</span><span>{activePack.match.map_name}</span></div>
              {editing ? <div className="edit-fields"><label>Memory title<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={100} /></label><label>What happened<textarea value={summary} onChange={(event) => setSummary(event.target.value)} maxLength={500} /></label><label>Player tags <small>Separate with commas</small><input value={tags} onChange={(event) => setTags(event.target.value)} /></label></div> : <><h2>{title}</h2><p className="memory-summary">{summary}</p><div className="tags">{tags.split(",").filter(Boolean).map((tag) => <span key={tag}>#{tag.trim()}</span>)}</div></>}
              <div className="human-signal"><span aria-hidden="true">&ldquo;</span><p><strong>Player-authored context</strong>{author?.display_name ?? "A player"} saved: &ldquo;{activePack.human_memory.caption}&rdquo;</p></div>
              {source === "live" && <div className="live-provenance">Generated by {result.metadata.model} in {result.metadata.elapsed_ms ? `${(result.metadata.elapsed_ms / 1000).toFixed(1)}s` : "this live run"}</div>}
            </div>
          </article>

          <div className="section-heading"><div><span>01</span><div><h3>Why we remember this</h3><p>Every sentence traces back to match data.</p></div></div><span className="grounding-score">{scoreLabel(result.validation.scores.evidence_grounding ?? 0)} evidence grounded</span></div>
          <div className="evidence-grid">{result.memory.evidence.map((evidence, index) => { const event = events.get(evidence.event_id); return <article className="evidence-card" key={`${evidence.event_id}-${index}`}><div className="evidence-number">{String(index + 1).padStart(2, "0")}</div><div><div className="evidence-type">{prettyEvent(evidence.event_type)}</div><p>{evidence.significance}</p><small>{event?.location ?? activePack.match.map_name} / {formatMatchTime(event?.timestamp_seconds)}</small></div><span className="verified">OK</span></article>; })}</div>

          <div className="section-heading"><div><span>02</span><div><h3>{activePack.squad.members.length} players, {activePack.squad.members.length} memories</h3><p>Each message reflects that player&apos;s role in the same moment.</p></div></div></div>
          <div className="perspective-grid">{result.player_perspectives.map((perspective, index) => <article className="perspective-card" key={perspective.player_id}><div className={`avatar avatar-${index % 4}`}>{perspective.display_name.at(0)}</div><div className="perspective-copy"><div><h4>{perspective.display_name}</h4><span>{activePack.squad.members.find((member) => member.player_id === perspective.player_id)?.role.replaceAll("_", " ") ?? "squadmate"}</span></div><p>{perspective.message}</p><small>Based on {perspective.evidence_event_ids.length} verified event{perspective.evidence_event_ids.length === 1 ? "" : "s"}</small></div></article>)}</div>

          <div className="section-heading quest-heading"><div><span>03</span><div><h3>The next chapter</h3><p>A playable remix of the original moment.</p></div></div><span className="recipe">{result.next_chapter.recipe}</span></div>
          <article className="quest-card"><div className="quest-intro"><span className="quest-kicker">SQUAD MISSION</span><h3>{result.next_chapter.title}</h3><p>{result.next_chapter.mission}</p><div className="quest-stats"><span><strong>{result.next_chapter.objectives.length}</strong> objectives</span><span><strong>{activePack.squad.members.length}</strong> squadmates</span><span><strong>1</strong> shared story</span></div></div><div className="objectives">{result.next_chapter.objectives.map((objective, index) => <div className="objective" key={objective.objective_id}><span className="objective-check">{index + 1}</span><div><strong>{objective.description}</strong><small>{objective.required ? "Required" : "Bonus"} / Verified from match telemetry</small></div></div>)}</div></article>

          <div className="quality-strip">{Object.entries(result.validation.scores).map(([label, score]) => <div key={label}><span>{prettyEvent(label)}</span><strong>{scoreLabel(score)}</strong><i><b style={{ width: scoreLabel(score) }} /></i></div>)}</div>
          <footer className="review-actions"><div><strong>Your call.</strong><span>Only confirmed memories become reunion invitations.</span></div><div className="action-buttons"><button className="dismiss" type="button" disabled={saving} onClick={() => void saveReview("dismissed")}>Dismiss</button>{editing ? <><button className="edit" type="button" onClick={() => setEditing(false)}>Cancel</button><button className="confirm" type="button" disabled={saving || !title.trim() || !summary.trim()} onClick={() => void saveReview("edited")}>{saving ? "Saving..." : "Save edits"}</button></> : <><button className="edit" type="button" onClick={() => setEditing(true)}>Edit memory</button><button className="confirm" type="button" disabled={saving} onClick={() => void saveReview("confirmed")}>{saving ? "Saving..." : "Yes, this is ours"}</button></>}</div></footer>
        </section>
      </div>
    </main>
  );
}
