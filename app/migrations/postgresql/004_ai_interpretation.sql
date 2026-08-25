CREATE TABLE ai_interpretations (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    external_message_id TEXT NOT NULL,
    profile_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    response_id TEXT NOT NULL,
    intent TEXT NOT NULL,
    interpretation_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider, external_message_id)
);

CREATE TABLE pending_actions (
    id BIGSERIAL PRIMARY KEY,
    contact_id BIGINT NOT NULL UNIQUE
        REFERENCES messaging_contacts(id) ON DELETE CASCADE,
    action_json TEXT NOT NULL,
    confirmation_prompt TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
