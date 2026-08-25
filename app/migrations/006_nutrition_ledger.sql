BEGIN;

CREATE TABLE nutrition_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    effective_from TEXT NOT NULL,
    calories_kcal REAL NOT NULL CHECK (calories_kcal >= 0),
    protein_g REAL NOT NULL CHECK (protein_g >= 0),
    carbohydrates_g REAL NOT NULL CHECK (carbohydrates_g >= 0),
    fat_g REAL NOT NULL CHECK (fat_g >= 0),
    fiber_g REAL NOT NULL CHECK (fiber_g >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (profile_id, effective_from)
);

CREATE INDEX nutrition_targets_profile_date_idx
    ON nutrition_targets(profile_id, effective_from);

CREATE TABLE meal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    eaten_at TEXT NOT NULL,
    calories_kcal REAL NOT NULL CHECK (calories_kcal >= 0),
    protein_g REAL NOT NULL CHECK (protein_g >= 0),
    carbohydrates_g REAL NOT NULL CHECK (carbohydrates_g >= 0),
    fat_g REAL NOT NULL CHECK (fat_g >= 0),
    fiber_g REAL NOT NULL CHECK (fiber_g >= 0),
    notes TEXT,
    value_source TEXT NOT NULL
        CHECK (value_source IN ('user_supplied', 'ai_estimate')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX meal_entries_profile_eaten_at_idx
    ON meal_entries(profile_id, eaten_at);
