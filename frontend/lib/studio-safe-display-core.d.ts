export type StudioSafePlayer = {
  player_id: string;
  display_name: string;
};

export function safeStudioRuleTarget(
  target: string | number | boolean | string[],
  players: StudioSafePlayer[],
): string;
