/** Cloudflare Worker entry point for the vinext-starter template. */
import { handleImageOptimization, DEFAULT_DEVICE_SIZES, DEFAULT_IMAGE_SIZES } from "vinext/server/image-optimization";
import handler from "vinext/server/app-router-entry";

interface Env {
  ASSETS: Fetcher;
  DB: D1Database;
  IMAGES: {
    input(stream: ReadableStream): {
      transform(options: Record<string, unknown>): {
        output(options: { format: string; quality: number }): Promise<{ response(): Response }>;
      };
    };
  };
}

interface ExecutionContext {
  waitUntil(promise: Promise<unknown>): void;
  passThroughOnException(): void;
}

const createReviewsTableSql = `CREATE TABLE IF NOT EXISTS memory_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pack_id TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('confirmed', 'edited', 'dismissed')),
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  tags_json TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)`;

const createReviewsIndexSql = `CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_reviews_pack_id
ON memory_reviews(pack_id)`;

async function ensureReviewsSchema(database: D1Database) {
  await database.batch([
    database.prepare(createReviewsTableSql),
    database.prepare(createReviewsIndexSql),
  ]);
}

async function handleReviews(request: Request, database: D1Database) {
  await ensureReviewsSchema(database);

  if (request.method === "GET") {
    const packId = new URL(request.url).searchParams.get("packId");
    const query = packId
      ? database.prepare("SELECT * FROM memory_reviews WHERE pack_id = ? LIMIT 1").bind(packId)
      : database.prepare("SELECT * FROM memory_reviews ORDER BY updated_at DESC LIMIT 20");
    const result = await query.all();
    return Response.json({ reviews: result.results });
  }

  if (request.method === "POST") {
    const payload = (await request.json()) as {
      packId?: string;
      decision?: "confirmed" | "edited" | "dismissed";
      title?: string;
      summary?: string;
      tags?: string[];
    };

    if (!payload.packId || !payload.decision || !payload.title?.trim() || !payload.summary?.trim()) {
      return Response.json({ error: "packId, decision, title, and summary are required" }, { status: 400 });
    }

    await database.prepare(`INSERT INTO memory_reviews (pack_id, decision, title, summary, tags_json, updated_at)
      VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(pack_id) DO UPDATE SET
        decision = excluded.decision,
        title = excluded.title,
        summary = excluded.summary,
        tags_json = excluded.tags_json,
        updated_at = CURRENT_TIMESTAMP`)
      .bind(payload.packId, payload.decision, payload.title.trim(), payload.summary.trim(), JSON.stringify(payload.tags ?? []))
      .run();

    return Response.json({ saved: true, decision: payload.decision }, { status: 201 });
  }

  return new Response("Method not allowed", { status: 405, headers: { Allow: "GET, POST" } });
}

// Image security config. SVG sources with .svg extension auto-skip the
// optimization endpoint on the client side (served directly, no proxy).
// To route SVGs through the optimizer (with security headers), set
// dangerouslyAllowSVG: true in next.config.js and uncomment below:
// const imageConfig: ImageConfig = { dangerouslyAllowSVG: true };

const worker = {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/api/reviews") {
      return handleReviews(request, env.DB);
    }

    if (url.pathname === "/_vinext/image") {
      const allowedWidths = [...DEFAULT_DEVICE_SIZES, ...DEFAULT_IMAGE_SIZES];
      return handleImageOptimization(request, {
        fetchAsset: (path) => env.ASSETS.fetch(new Request(new URL(path, request.url))),
        transformImage: async (body, { width, format, quality }) => {
          const result = await env.IMAGES.input(body).transform(width > 0 ? { width } : {}).output({ format, quality });
          return result.response();
        },
      }, allowedWidths);
    }

    return handler.fetch(request, env, ctx);
  },
};

export default worker;
