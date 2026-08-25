BEGIN;

CREATE TABLE messaging_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    address TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider, address),
    UNIQUE (profile_id, provider)
);

CREATE INDEX messaging_contacts_profile_id_idx
    ON messaging_contacts(profile_id);

CREATE TABLE inbound_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    contact_id INTEGER REFERENCES messaging_contacts(id) ON DELETE SET NULL,
    from_address TEXT NOT NULL,
    to_address TEXT NOT NULL,
    body TEXT NOT NULL,
    reply_body TEXT,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider, external_id)
);

CREATE TABLE outbound_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    contact_id INTEGER NOT NULL
        REFERENCES messaging_contacts(id) ON DELETE CASCADE,
    from_address TEXT NOT NULL,
    to_address TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider, external_id)
);
