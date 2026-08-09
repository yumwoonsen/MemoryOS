const noStoreHeaders = { "cache-control": "no-store" };

export async function POST() {
  return Response.json(
    {
      stage: "studio_scenario",
      code: "studio_scenario_required",
      retryable: false,
      message: "Select and prepare a versioned Studio scenario before starting a live interpretation.",
    },
    { status: 410, headers: noStoreHeaders },
  );
}
