"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import type { MemoryPackV11 } from "@/lib/history-types";

type Delivery = {
  delivery_id: string;
  status: "pending_player_decision";
  memory: { title: string; summary: string; evidence: Array<{ event_id: string; significance: string }> };
  player_perspectives: Array<{ player_id: string; message: string }>;
  next_chapter: { title: string; mission: string; objectives: Array<{ objective_id: string; description: string; required: boolean }> };
  narrative: { teaser: string; why_this_surfaced: string };
};

type View =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "inbox"; delivery: Delivery }
  | { kind: "decline"; delivery: Delivery }
  | { kind: "sending"; delivery: Delivery; decision: "accepted" | "declined" }
  | { kind: "accepted"; delivery: Delivery }
  | { kind: "declined" };

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isDelivery(value: unknown): value is Delivery {
  return isRecord(value)
    && value.status === "pending_player_decision"
    && typeof value.delivery_id === "string"
    && isRecord(value.memory)
    && typeof value.memory.title === "string"
    && typeof value.memory.summary === "string"
    && Array.isArray(value.player_perspectives)
    && isRecord(value.next_chapter)
    && isRecord(value.narrative);
}

export function HistoryExperience({ initialPacks }: { initialPacks: MemoryPackV11[] }) {
  const [view, setView] = useState<View>({ kind: "loading" });

  const prepare = useCallback(async () => {
    try {
      const response = await fetch("/api/delivery/prepare", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ schema_version: "1.1", memory_packs: initialPacks }),
      });
      const payload: unknown = await response.json();
      if (!response.ok || !isDelivery(payload)) throw new Error("Your squad memory is not available right now.");
      setView({ kind: "inbox", delivery: payload });
    } catch (error) {
      setView({ kind: "error", message: error instanceof Error ? error.message : "Your squad memory is not available right now." });
    }
  }, [initialPacks]);

  useEffect(() => {
    const timer = window.setTimeout(() => void prepare(), 0);
    return () => window.clearTimeout(timer);
  }, [prepare]);

  async function decide(decision: "accepted" | "declined", declineReason?: "not_relevant" | "details_wrong") {
    if (view.kind !== "inbox" && view.kind !== "decline") return;
    const delivery = view.delivery;
    setView({ kind: "sending", delivery, decision });
    try {
      const response = await fetch("/api/delivery/decision", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ delivery_id: delivery.delivery_id, decision, decline_reason: declineReason }),
      });
      if (!response.ok) throw new Error("Your choice could not be saved safely.");
      setView(decision === "accepted" ? { kind: "accepted", delivery } : { kind: "declined" });
    } catch (error) {
      setView({ kind: "error", message: error instanceof Error ? error.message : "Your choice could not be saved safely." });
    }
  }

  return <main className="player-app history-app" data-theme="light" data-game="free-fire">
    <a className="skip-link" href="#memory-inbox">Skip to your memory</a>
    <div className="player-mode-heading">Battle Royale</div>
    <div className="player-shell"><header className="player-topbar"><Link className="player-brand" href="/" aria-label="MemoryOS player home"><span className="player-brand-mark">M</span><span>MemoryOS</span></Link><span className={`engine-badge ${view.kind === "loading" || view.kind === "sending" ? "checking" : ""}`}><i aria-hidden="true" />{view.kind === "accepted" ? "Mission ready" : "Memory inbox"}</span></header>
      <div className="player-page" id="memory-inbox" aria-busy={view.kind === "loading" || view.kind === "sending"}>
        {view.kind === "loading" && <section className="demo-processing-card" role="status"><div className="demo-processing-mark" aria-hidden="true">M</div><p className="demo-kicker">Memory inbox</p><h1>Bringing a squad moment back.</h1><p className="reveal-loading-copy">Preparing a grounded memory and a new chapter for your squad.</p></section>}
        {view.kind === "error" && <StateCard title="Your memory is unavailable" message={view.message} action="Try again" onAction={() => void prepare()} />}
        {view.kind === "inbox" && <MemoryCard delivery={view.delivery} onAccept={() => void decide("accepted")} onDecline={() => setView({ kind: "decline", delivery: view.delivery })} />}
        {view.kind === "decline" && <section className="history-intro" aria-labelledby="decline-title"><p className="demo-kicker">Not for you?</p><h1 id="decline-title">Help MemoryOS improve the next memory.</h1><p>This will dismiss the mission. It will not change your match history.</p><div className="review-actions"><button className="secondary-action" type="button" onClick={() => void decide("declined", "not_relevant")}>Not relevant to me</button><button className="secondary-action" type="button" onClick={() => void decide("declined", "details_wrong")}>Details are wrong</button></div></section>}
        {view.kind === "sending" && <section className="demo-processing-card" role="status"><div className="demo-processing-mark" aria-hidden="true">M</div><p className="demo-kicker">Saving your choice</p><h1>{view.decision === "accepted" ? "Your squad has a new chapter." : "This memory will stay in the past."}</h1></section>}
        {view.kind === "accepted" && <section className="history-intro" aria-labelledby="mission-title"><p className="demo-kicker">Mission ready</p><h1 id="mission-title">{view.delivery.next_chapter.title}</h1><p>{view.delivery.next_chapter.mission}</p><button className="reveal-memory-button" type="button">Mission accepted</button></section>}
        {view.kind === "declined" && <StateCard title="Thanks for letting us know." message="This mission has been dismissed. Your feedback will help make future memories more relevant." action="Back to your memory" onAction={() => void prepare()} />}
        <footer className="player-footer"><span>MemoryOS</span><p>Your squad’s history, made personal.</p></footer>
      </div></div>
  </main>;
}

function MemoryCard({ delivery, onAccept, onDecline }: { delivery: Delivery; onAccept: () => void; onDecline: () => void }) {
  const perspective = delivery.player_perspectives[0];
  return <><section className="player-hero" aria-labelledby="memory-title"><div className="player-memory-copy"><p className="demo-kicker">A memory from your squad</p><div className="memory-gist-label">{delivery.narrative.teaser}</div><h1 id="memory-title">{delivery.memory.title}</h1><p>{delivery.memory.summary}</p><p className="history-note">{delivery.narrative.why_this_surfaced}</p></div></section>{perspective && <section className="player-section your-perspective-card"><h2>Your side of the story</h2><p className="your-message">{perspective.message}</p></section>}<section className="player-section player-next"><div className="next-chapter-label">A new chapter</div><h2>{delivery.next_chapter.title}</h2><p className="player-next-mission">{delivery.next_chapter.mission}</p></section><div className="review-actions"><button className="reveal-memory-button" type="button" onClick={onAccept}>Accept mission</button><button className="secondary-action" type="button" onClick={onDecline}>Decline</button></div></>;
}

function StateCard({ title, message, action, onAction }: { title: string; message: string; action: string; onAction: () => void }) {
  return <section className="player-state-card" role="alert"><span>Memory inbox</span><h1>{title}</h1><p>{message}</p><button type="button" onClick={onAction}>{action}</button></section>;
}
