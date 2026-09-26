-- Recipe knowledge base. Bilingual text lives in *_json columns as {"el": ..., "en": ...},
-- mirroring the Pydantic models in app/schemas.py.
--
-- status: 'staged'    - imported, not yet reviewed; never served by /recipes or used by /analyze
--         'published' - a human curated the safety-relevant fields (DESIGN.md #4)

CREATE TABLE recipes (
    id               TEXT PRIMARY KEY
                     CHECK (length(id) BETWEEN 1 AND 64
                            AND substr(id, 1, 1) GLOB '[a-z0-9]'
                            AND id NOT GLOB '*[^a-z0-9_-]*'),
    status           TEXT NOT NULL DEFAULT 'staged' CHECK (status IN ('staged', 'published')),
    name_json        TEXT NOT NULL,
    aliases_json     TEXT NOT NULL DEFAULT '{}',
    description_json TEXT NOT NULL DEFAULT '{}',
    language         TEXT,
    servings         TEXT,
    prep_min         INTEGER,
    cook_min         INTEGER,
    total_min        INTEGER,
    difficulty       TEXT,
    cuisine          TEXT,
    category         TEXT,
    image_url        TEXT,
    video_url        TEXT,
    nutrition_json   TEXT NOT NULL DEFAULT '{}',
    dietary_json     TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX recipes_status ON recipes (status);

-- Where a recipe came from. url is unique so a re-import updates instead of duplicating.
CREATE TABLE recipe_sources (
    recipe_id   TEXT NOT NULL REFERENCES recipes (id) ON DELETE CASCADE ON UPDATE CASCADE,
    site        TEXT NOT NULL,
    source_id   TEXT,
    url         TEXT NOT NULL UNIQUE,
    url_json    TEXT NOT NULL DEFAULT '{}',  -- per-language URLs when the site has them
    author      TEXT,
    fetched_at  TEXT,
    imported_at TEXT,
    raw_json    TEXT  -- the full scraped payload, kept for provenance and re-curation
);
CREATE INDEX recipe_sources_recipe ON recipe_sources (recipe_id);

CREATE TABLE steps (
    recipe_id              TEXT NOT NULL REFERENCES recipes (id) ON DELETE CASCADE ON UPDATE CASCADE,
    idx                    INTEGER NOT NULL,
    section                TEXT,
    instruction_json       TEXT NOT NULL,
    expected_duration_sec  INTEGER,
    suggested_duration_sec INTEGER,  -- parsed from the text at import; the curator confirms
    checkable              INTEGER NOT NULL DEFAULT 0,
    check_prompt_hint      TEXT,
    reference_image        TEXT,
    contains_raw_protein   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (recipe_id, idx)
);

CREATE TABLE recipe_ingredients (
    recipe_id  TEXT NOT NULL REFERENCES recipes (id) ON DELETE CASCADE ON UPDATE CASCADE,
    position   INTEGER NOT NULL,
    group_name TEXT,
    raw_text   TEXT NOT NULL,
    quantity   TEXT,
    unit       TEXT,
    name       TEXT,
    vocab_id   TEXT,  -- detector class (app/detection/vocabulary.json), when one matches
    PRIMARY KEY (recipe_id, position)
);

CREATE TABLE recipe_equipment (
    recipe_id TEXT NOT NULL REFERENCES recipes (id) ON DELETE CASCADE ON UPDATE CASCADE,
    name      TEXT NOT NULL,
    vocab_id  TEXT,
    inferred  INTEGER NOT NULL DEFAULT 0,  -- 1 = guessed from the step text, not listed by the source
    PRIMARY KEY (recipe_id, name)
);
