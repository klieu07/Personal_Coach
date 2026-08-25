CREATE TABLE nutrition_targets (
    id BIGSERIAL PRIMARY KEY,
    profile_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    effective_from TEXT NOT NULL,
    calories_kcal DOUBLE PRECISION NOT NULL CHECK (calories_kcal >= 0),
    protein_g DOUBLE PRECISION NOT NULL CHECK (protein_g >= 0),
    carbohydrates_g DOUBLE PRECISION NOT NULL CHECK (carbohydrates_g >= 0),
    fat_g DOUBLE PRECISION NOT NULL CHECK (fat_g >= 0),
    fiber_g DOUBLE PRECISION NOT NULL CHECK (fiber_g >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (profile_id, effective_from)
);

CREATE INDEX nutrition_targets_profile_date_idx
    ON nutrition_targets(profile_id, effective_from);

CREATE TABLE meal_entries (
    id BIGSERIAL PRIMARY KEY,
    profile_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    eaten_at TEXT NOT NULL,
    calories_kcal DOUBLE PRECISION NOT NULL CHECK (calories_kcal >= 0),
    protein_g DOUBLE PRECISION NOT NULL CHECK (protein_g >= 0),
    carbohydrates_g DOUBLE PRECISION NOT NULL CHECK (carbohydrates_g >= 0),
    fat_g DOUBLE PRECISION NOT NULL CHECK (fat_g >= 0),
    fiber_g DOUBLE PRECISION NOT NULL CHECK (fiber_g >= 0),
    notes TEXT,
    value_source TEXT NOT NULL
        CHECK (value_source IN ('user_supplied', 'ai_estimate')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX meal_entries_profile_eaten_at_idx
    ON meal_entries(profile_id, eaten_at);
