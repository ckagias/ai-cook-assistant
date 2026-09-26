-- What the cook needs on the counter, read out before the first step: bilingual names like
-- recipe_ingredients.text_json. {"el": "θερμόμετρο κρέατος", "en": "meat thermometer"}; empty =
-- the detector vocabulary's label for vocab_id, else `name`.
ALTER TABLE recipe_equipment ADD COLUMN text_json TEXT NOT NULL DEFAULT '{}';
