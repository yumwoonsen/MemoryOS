const replaySchemaVersion = "1.0";
const resultSchemaVersion = "2.1";

function isRecord(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isIsoInstant(value) {
  return typeof value === "string"
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(value)
    && Number.isFinite(Date.parse(value));
}

export function exactStudioScenarioVersion(expected, actual) {
  return Boolean(
    isRecord(expected)
    && isRecord(actual)
    && expected.scenario_id === actual.scenario_id
    && expected.fixture_sha256 === actual.fixture_sha256
    && expected.fixture_revision === actual.fixture_revision,
  );
}

export function parseStudioReplayEnvelope(value, expectedScenario) {
  const resultStatus = isRecord(value) && isRecord(value.result)
    ? value.result.status
    : null;
  const expectedInnerOrigin = resultStatus === "pending_player_decision"
    ? "saved_live_replay"
    : ["not_generated", "rejected"].includes(resultStatus)
      ? "no_player_content"
      : null;
  if (!isRecord(value)
    || value.replay_schema_version !== replaySchemaVersion
    || !isRecord(value.scenario)
    || !exactStudioScenarioVersion(expectedScenario, value.scenario)
    || !isRecord(value.provenance)
    || typeof value.provenance.provider !== "string"
    || typeof value.provenance.model !== "string"
    || typeof value.provenance.prompt_version !== "string"
    || value.provenance.result_schema_version !== resultSchemaVersion
    || !isIsoInstant(value.provenance.captured_at)
    || !isRecord(value.result)
    || value.result.schema_version !== resultSchemaVersion
    || !isRecord(value.result.metadata)
    || expectedInnerOrigin === null
    || value.result.metadata.content_origin !== expectedInnerOrigin
    || value.result.metadata.mode !== "live_ai"
    || value.result.metadata.provider !== value.provenance.provider
    || value.result.metadata.model !== value.provenance.model
    || value.result.metadata.prompt_version !== value.provenance.prompt_version) return null;

  return value;
}

export function studioReplayArtifactsFromManifest(manifest) {
  if (!isRecord(manifest)
    || Object.keys(manifest).length !== 2
    || manifest.schema_version !== replaySchemaVersion
    || !Array.isArray(manifest.replays)) return null;
  return manifest.replays;
}
