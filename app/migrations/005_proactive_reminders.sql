BEGIN;

CREATE TABLE reminder_settings (
    profile_id INTEGER PRIMARY KEY
        REFERENCES profiles(id) ON DELETE CASCADE,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    reminder_time TEXT NOT NULL DEFAULT '08:00:00',
    quiet_hours_start TEXT NOT NULL DEFAULT '21:00:00',
    quiet_hours_end TEXT NOT NULL DEFAULT '07:00:00',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reminder_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    session_id INTEGER NOT NULL UNIQUE
        REFERENCES training_sessions(id) ON DELETE CASCADE,
    scheduled_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'processing', 'sent', 'failed', 'cancelled'
        )),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at TEXT,
    sent_external_id TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX reminder_jobs_due_idx
    ON reminder_jobs(status, next_attempt_at, scheduled_at);
CREATE INDEX reminder_jobs_profile_id_idx ON reminder_jobs(profile_id);
