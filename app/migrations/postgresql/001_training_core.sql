CREATE TABLE profiles (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    timezone TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE programs (
    id BIGSERIAL PRIMARY KEY,
    profile_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    discipline TEXT NOT NULL CHECK (discipline IN ('lifting', 'running')),
    active SMALLINT NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX programs_profile_id_idx ON programs(profile_id);

CREATE TABLE training_sessions (
    id BIGSERIAL PRIMARY KEY,
    program_id BIGINT NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    scheduled_for TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'completed', 'skipped')),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX training_sessions_program_id_idx ON training_sessions(program_id);
CREATE INDEX training_sessions_scheduled_for_idx
    ON training_sessions(scheduled_for);

CREATE TABLE workout_results (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL UNIQUE
        REFERENCES training_sessions(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
