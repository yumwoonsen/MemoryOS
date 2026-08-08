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
import type { ContinuationChapter, MissionVerification } from "@/lib/reunion-flow";

export type ChapterFeedback = "hidden";

export type ContinuationState = {
  verification: MissionVerification;
  chapter: ContinuationChapter;
  feedback: ChapterFeedback | null;
};

export type PlayerFlowState = {
  delivery: PendingDelivery | null;
  currentPlayerId: string | null;
  invitationPlayerIds: string[];
  missionAccepted: boolean;
  declineReason: DeliveryDeclineReason | null;
  invitationReadyIds: string[] | null;
  continuation: ContinuationState | null;
};

type PlayerFlowContextValue = {
  flow: PlayerFlowState;
  setPreparedDelivery: (delivery: PendingDelivery, currentPlayerId: string, invitationPlayerIds: string[]) => void;
  acceptMission: (delivery: PendingDelivery, currentPlayerId: string, invitationPlayerIds: string[]) => void;
  declineMission: (reason: DeliveryDeclineReason) => void;
  setInvitationReadyIds: (playerIds: string[]) => void;
  completeMission: (verification: MissionVerification, chapter: ContinuationChapter) => void;
  setChapterFeedback: (feedback: ChapterFeedback) => void;
};

const emptyFlow: PlayerFlowState = {
  delivery: null,
  currentPlayerId: null,
  invitationPlayerIds: [],
  missionAccepted: false,
  declineReason: null,
  invitationReadyIds: null,
  continuation: null,
};

const PlayerFlowContext = createContext<PlayerFlowContextValue | null>(null);

export function PlayerFlowProvider({ children }: { children: React.ReactNode }) {
  const [flow, setFlow] = useState<PlayerFlowState>(emptyFlow);

  const setPreparedDelivery = useCallback((
    delivery: PendingDelivery,
    currentPlayerId: string,
    invitationPlayerIds: string[],
  ) => {
    setFlow({
      delivery,
      currentPlayerId,
      invitationPlayerIds: [...new Set(invitationPlayerIds)],
      missionAccepted: false,
      declineReason: null,
      invitationReadyIds: null,
      continuation: null,
    });
  }, []);

  const acceptMission = useCallback((
    delivery: PendingDelivery,
    currentPlayerId: string,
    invitationPlayerIds: string[],
  ) => {
    setFlow((current) => ({
      delivery,
      currentPlayerId,
      invitationPlayerIds: [...new Set(invitationPlayerIds)],
      missionAccepted: true,
      declineReason: null,
      invitationReadyIds: current.delivery?.delivery_id === delivery.delivery_id
        ? current.invitationReadyIds
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
          invitationPlayerIds: [],
          invitationReadyIds: null,
          continuation: null,
        }
      : current);
  }, []);

  const setInvitationReadyIds = useCallback((playerIds: string[]) => {
    setFlow((current) => current.missionAccepted
      ? { ...current, invitationReadyIds: [...new Set(playerIds)] }
      : current);
  }, []);

  const completeMission = useCallback((verification: MissionVerification, chapter: ContinuationChapter) => {
    setFlow((current) => current.missionAccepted
      ? { ...current, continuation: { verification, chapter, feedback: null } }
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
    setInvitationReadyIds,
    completeMission,
    setChapterFeedback,
  }), [
    acceptMission,
    completeMission,
    declineMission,
    flow,
    setChapterFeedback,
    setInvitationReadyIds,
    setPreparedDelivery,
  ]);

  return <PlayerFlowContext.Provider value={value}>{children}</PlayerFlowContext.Provider>;
}

export function usePlayerFlow() {
  const value = useContext(PlayerFlowContext);
  if (!value) throw new Error("usePlayerFlow must be used inside PlayerFlowProvider");
  return value;
}
