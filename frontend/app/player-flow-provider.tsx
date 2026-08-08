"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";

import type { PendingDelivery } from "@/lib/delivery-flow";
import type { DeliveryDeclineReason } from "@/lib/delivery-flow";
import type {
  ContinuationChapter,
  InvitationResponse,
  PrototypeMatchOutcome,
} from "@/lib/reunion-flow";

export type ChapterFeedback = "hidden";

export type ContinuationState = {
  outcome: PrototypeMatchOutcome;
  chapter: ContinuationChapter;
  feedback: ChapterFeedback | null;
};

export type InvitationSession = {
  state: "sent" | "lobby_ready" | "match_started" | "completed";
  recipients: InvitationResponse[];
};

export type PlayerFlowState = {
  delivery: PendingDelivery | null;
  missionAccepted: boolean;
  declineReason: DeliveryDeclineReason | null;
  invitationSession: InvitationSession | null;
  continuation: ContinuationState | null;
};

type PlayerFlowContextValue = {
  flow: PlayerFlowState;
  setPreparedDelivery: (delivery: PendingDelivery) => void;
  acceptMission: (delivery: PendingDelivery) => void;
  declineMission: (reason: DeliveryDeclineReason) => void;
  openInvitation: () => void;
  acceptAllInvitees: () => void;
  startPrototypeMatch: () => void;
  completeMission: (outcome: PrototypeMatchOutcome, chapter: ContinuationChapter) => void;
  setChapterFeedback: (feedback: ChapterFeedback) => void;
};

const emptyFlow: PlayerFlowState = {
  delivery: null,
  missionAccepted: false,
  declineReason: null,
  invitationSession: null,
  continuation: null,
};

const PlayerFlowContext = createContext<PlayerFlowContextValue | null>(null);

export function PlayerFlowProvider({ children }: { children: React.ReactNode }) {
  const [flow, setFlow] = useState<PlayerFlowState>(emptyFlow);

  const setPreparedDelivery = useCallback((delivery: PendingDelivery) => {
    setFlow({
      delivery,
      missionAccepted: false,
      declineReason: null,
      invitationSession: null,
      continuation: null,
    });
  }, []);

  const acceptMission = useCallback((delivery: PendingDelivery) => {
    setFlow((current) => ({
      delivery,
      missionAccepted: true,
      declineReason: null,
      invitationSession: current.delivery?.delivery_id === delivery.delivery_id
        ? current.invitationSession
        : null,
      continuation: current.delivery?.delivery_id === delivery.delivery_id
        ? current.continuation
        : null,
    }));
  }, []);

  const declineMission = useCallback((reason: DeliveryDeclineReason) => {
    setFlow((current) => current.delivery
      ? {
          ...current,
          missionAccepted: false,
          declineReason: reason,
          invitationSession: null,
          continuation: null,
        }
      : current);
  }, []);

  const openInvitation = useCallback(() => {
    setFlow((current) => {
      if (!current.missionAccepted || !current.delivery) return current;
      const recipients: InvitationResponse[] = current.delivery.invitation_roster.map((recipient) => ({
        recipient_ref: recipient.recipient_ref,
        response: recipient.is_current_player ? "self_joined" : "pending",
      }));
      return {
        ...current,
        invitationSession: {
          state: recipients.every((recipient) => recipient.response !== "pending") ? "lobby_ready" : "sent",
          recipients,
        },
      };
    });
  }, []);

  const acceptAllInvitees = useCallback(() => {
    setFlow((current) => current.invitationSession?.state === "sent"
      ? {
          ...current,
          invitationSession: {
            state: "lobby_ready",
            recipients: current.invitationSession.recipients.map((recipient) => ({
              ...recipient,
              response: recipient.response === "pending" ? "joined" : recipient.response,
            })),
          },
        }
      : current);
  }, []);

  const startPrototypeMatch = useCallback(() => {
    setFlow((current) => current.invitationSession?.state === "lobby_ready"
      ? {
          ...current,
          invitationSession: { ...current.invitationSession, state: "match_started" },
        }
      : current);
  }, []);

  const completeMission = useCallback((outcome: PrototypeMatchOutcome, chapter: ContinuationChapter) => {
    setFlow((current) => current.missionAccepted
      ? {
          ...current,
          invitationSession: current.invitationSession
            ? { ...current.invitationSession, state: "completed" }
            : current.invitationSession,
          continuation: { outcome, chapter, feedback: null },
        }
      : current);
  }, []);

  const setChapterFeedback = useCallback((feedback: ChapterFeedback) => {
    setFlow((current) => current.continuation
      ? { ...current, continuation: { ...current.continuation, feedback } }
      : current);
  }, []);

  const value = useMemo<PlayerFlowContextValue>(() => ({
    flow,
    setPreparedDelivery,
    acceptMission,
    declineMission,
    openInvitation,
    acceptAllInvitees,
    startPrototypeMatch,
    completeMission,
    setChapterFeedback,
  }), [
    acceptMission,
    acceptAllInvitees,
    completeMission,
    declineMission,
    flow,
    openInvitation,
    setChapterFeedback,
    setPreparedDelivery,
    startPrototypeMatch,
  ]);

  return <PlayerFlowContext.Provider value={value}>{children}</PlayerFlowContext.Provider>;
}

export function usePlayerFlow() {
  const value = useContext(PlayerFlowContext);
  if (!value) throw new Error("usePlayerFlow must be used inside PlayerFlowProvider");
  return value;
}
