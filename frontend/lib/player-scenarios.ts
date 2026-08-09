/**
 * Browser-safe identifier for the one player-facing squad signal.
 *
 * The telemetry binding intentionally lives in player-scenario.server.ts so
 * importing this type into a client component cannot pull a fixture or a
 * scenario registry into the browser bundle.
 */
export type PlayerExperienceRef = "squad-signal-01";
