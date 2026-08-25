CREATE TABLE lifting_exercises (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL
        REFERENCES training_sessions(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    name TEXT NOT NULL,
    sets INTEGER NOT NULL CHECK (sets > 0),
    reps INTEGER NOT NULL CHECK (reps > 0),
    target_weight_kg DOUBLE PRECISION,
    rest_seconds INTEGER,
    UNIQUE (session_id, position)
);

CREATE INDEX lifting_exercises_session_id_idx
    ON lifting_exercises(session_id);

CREATE TABLE running_segments (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL
        REFERENCES training_sessions(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (
        kind IN ('warmup', 'work', 'recovery', 'steady', 'cooldown')
    ),
    distance_m INTEGER,
    duration_seconds INTEGER,
    target_pace_seconds_per_km INTEGER,
    CHECK (distance_m IS NOT NULL OR duration_seconds IS NOT NULL),
    UNIQUE (session_id, position)
);

CREATE INDEX running_segments_session_id_idx
    ON running_segments(session_id);

CREATE TABLE lifting_set_results (
    id BIGSERIAL PRIMARY KEY,
    result_id BIGINT NOT NULL
        REFERENCES workout_results(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    exercise_name TEXT NOT NULL,
    set_number INTEGER NOT NULL,
    reps INTEGER NOT NULL,
    weight_kg DOUBLE PRECISION,
    UNIQUE (result_id, position)
);

CREATE INDEX lifting_set_results_result_id_idx
    ON lifting_set_results(result_id);

CREATE TABLE running_result_metrics (
    result_id BIGINT PRIMARY KEY
        REFERENCES workout_results(id) ON DELETE CASCADE,
    distance_m INTEGER NOT NULL,
    duration_seconds INTEGER NOT NULL,
    average_heart_rate INTEGER
);
