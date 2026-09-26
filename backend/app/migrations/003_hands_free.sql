-- Hands-free cooking: what a check judges, doneness targets for meat, bilingual ingredient
-- lines, and a small key/value table so a changed data/recipes.json reaches existing databases.

-- 'prep' (cutting, mixing): a check judges the work, never doneness. NULL = not curated.
ALTER TABLE steps ADD COLUMN kind TEXT CHECK (kind IN ('prep', 'cook', 'rest'));
-- {"medium_rare": {"temp_c": 54, "duration_sec": 2400}, ...} - curated, like contains_raw_protein.
ALTER TABLE steps ADD COLUMN by_doneness_json TEXT NOT NULL DEFAULT '{}';
-- {"el": "1,5 κιλό μοσχάρι", "en": "1.5 kg beef"}; raw_text stays the source's own line.
ALTER TABLE recipe_ingredients ADD COLUMN text_json TEXT NOT NULL DEFAULT '{}';

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
