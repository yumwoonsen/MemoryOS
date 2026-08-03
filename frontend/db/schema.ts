import { sql } from "drizzle-orm";
import { integer, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const reviews = sqliteTable("memory_reviews", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  packId: text("pack_id").notNull(),
  decision: text("decision", { enum: ["confirmed", "edited", "dismissed"] }).notNull(),
  title: text("title").notNull(),
  summary: text("summary").notNull(),
  tags: text("tags_json").notNull().default("[]"),
  updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
}, (table) => [uniqueIndex("idx_memory_reviews_pack_id").on(table.packId)]);
