-- Full-text recipe search, ranked with SQLite's built-in BM25 (no embeddings, no new
-- dependency). `body` holds accent-folded text (app/recipes.py writes it through the same
-- fold() used everywhere else), so Greek matches with or without tonos. Kept in step with
-- `recipes` by recipes.save_recipe/delete_recipe; ensure_ready() rebuilds it if they differ.
CREATE VIRTUAL TABLE recipe_search USING fts5(recipe_id UNINDEXED, body);
