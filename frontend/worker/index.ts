import handler from "vinext/server/app-router-entry";

// The current prototype uses pre-optimized WebPs, so the app router is the
// only Worker entry point it needs.
export default handler;
