BEGIN;

CREATE TABLE ai_interpretations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    external_message_id TEXT NOT NULL,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    response_id TEXT NOT NULL,
    intent TEXT NOT NULL,
    interpretation_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider, external_message_id)
);

CREATE TABLE pending_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL UNIQUE
        REFERENCES messaging_contacts(id) ON DELETE CASCADE,
    action_json TEXT NOT NULL,
    confirmation_prompt TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
