CREATE TABLE `memory_reviews` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`pack_id` text NOT NULL,
	`decision` text NOT NULL,
	`title` text NOT NULL,
	`summary` text NOT NULL,
	`tags_json` text DEFAULT '[]' NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_memory_reviews_pack_id` ON `memory_reviews` (`pack_id`);