export type MemoryStatus =
  | "ready"
  | "needs_human_confirmation"
  | "rejected";

export type MemoryPack = {
  schema_version: "1.0" | "1.1";
  pack_id: string;
  player_profile: {
    player_id: string;
    preferred_role?: string | null;
  };
  squad: {
    squad_id: string;
    members: Array<{
      player_id: string;
      display_name: string;
      role?: string | null;
      opted_in?: boolean;
    }>;
    matches_together: number;
    days_since_full_squad?: number | null;
  };
  match: {
    match_id: string;
    mode: string;
    map_name?: string | null;
    placement?: number | null;
    played_at?: string | null;
  };
  match_events: Array<{
    event_id: string;
    type: string;
    actor_id?: string | null;
    target_id?: string | null;
    timestamp_seconds?: number | null;
    location?: string | null;
    importance?: "low" | "medium" | "high";
    details?: Record<string, string | number | boolean>;
  }>;
  human_memory?: {
    caption?: string | null;
    tags?: string[];
    author_player_id?: string | null;
    confirmed?: boolean;
  } | null;
  human_review?: {
    source_status: "unreviewed" | "verified" | "disputed";
    meaning_status: "unreviewed" | "confirmed" | "dismissed";
  };
  reactions?: {
    laugh_count?: number;
    fire_count?: number;
    saved?: boolean;
  };
  current_context?: {
    active_member_ids?: string[];
    resurfacing_reason?: string | null;
    original_mode_available?: boolean;
  };
};

export type DiscoveryAssessment = {
  signal_score: number;
  threshold: number;
  reasons: string[];
  eligible: boolean;
};

export type MemoryRecord = {
  title: string;
  memory_type: "chaos" | "comeback" | "clutch" | "ritual" | "first" | "other";
  summary: string;
  confidence: number;
  evidence: Array<{
    event_id: string;
    event_type: string;
    significance: string;
  }>;
  human_confirmed?: boolean;
};

export type PlayerPerspective = {
  player_id: string;
  display_name: string;
  message: string;
  evidence_event_ids: string[];
};

export type QuestObjective = {
  objective_id: string;
  description: string;
  assigned_player_id?: string;
  required: boolean;
  verification: {
    metric: string;
    operator: "equals" | "at_least" | "contains_all";
    target: string | number | boolean | string[];
  };
  source_event_ids: string[];
};

export type PipelineMetadata = {
  pipeline_version: string;
  provider: string;
  model: string;
  prompt_version?: string;
  factual_renderer: string;
  redaction_count?: number;
  compatibility_conversion?: string;
  stopped_stage?: string;
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
    [key: string]: number | undefined;
  };
};

export type MemoryApiError = {
  code: string;
  message: string;
};

export type MemoryEngineResult = {
  schema_version: "1.0";
  pack_id: string;
  status: MemoryStatus;
  discovery: DiscoveryAssessment;
  memory?: MemoryRecord;
  player_perspectives: PlayerPerspective[];
  next_chapter?: {
    title: string;
    mission: string;
    recipe: "recreate" | "remix" | "resolve";
    objectives: QuestObjective[];
  };
  validation: {
    passed: boolean;
    human_review_required: boolean;
    scores: {
      specificity: number;
      evidence_grounding: number;
      perspective_distinctness: number;
      quest_connection: number;
    };
    issues: Array<{
      code: string;
      severity: "info" | "warning" | "error";
      message: string;
    }>;
  };
  metadata: PipelineMetadata;
};

export type DeveloperPipelineStatus =
  | MemoryStatus
  | "needs_source_verification"
  | "needs_meaning_confirmation";

export type DeveloperMemoryEngineResult = Omit<
  MemoryEngineResult,
  "schema_version" | "status" | "metadata"
> & {
  schema_version: "1.0" | "1.1";
  status: DeveloperPipelineStatus;
  source_status?: "unreviewed" | "verified" | "disputed";
  meaning_status?: "unreviewed" | "confirmed" | "dismissed";
  metadata: PipelineMetadata;
};

export type DeveloperStageName =
  | "review_and_discovery"
  | "memory_discovery"
  | "perspectives"
  | "quest_generation"
  | "validation";

export type DeveloperStageEvent = {
  type: "stage";
  stage: DeveloperStageName;
  status: "working" | "complete" | "stopped" | "failed";
  message?: string;
  preview?: unknown;
};

export type DeveloperErrorEvent = {
  type: "error";
  stage: string;
  code: string;
  retryable: boolean;
  message?: string;
};

export type DeveloperResultEvent = {
  type: "result";
  result: DeveloperMemoryEngineResult;
};

export type DeveloperStreamEvent =
  | DeveloperStageEvent
  | DeveloperErrorEvent
  | DeveloperResultEvent;

export type DeveloperHealth = {
  status: "ok" | "sample" | "error";
  mode: "live" | "sample";
  provider: string;
  model: string;
  message: string;
  code?: string;
};
