-- Audit log + idempotency store for simulated side effects (action dispatcher).
-- Runtime table: excluded from db/seed.dump, re-applied every start, hence "if not exists".
-- Status is validated by a Pydantic StrEnum, not a CHECK.

create table if not exists simulated_actions (
    id uuid primary key,
    conversation_id uuid not null references conversations on delete restrict,
    message_id uuid null,
    idempotency_key text not null unique,
    kind text not null,
    approval_id uuid null references approvals on delete restrict,
    payload jsonb not null,
    status text not null,
    result jsonb null,
    claimed_at timestamptz not null,
    completed_at timestamptz null,
    constraint simulated_actions_message_conversation_fk
        foreign key (message_id, conversation_id) references messages (id, conversation_id)
        on delete restrict
);
create index if not exists simulated_actions_conversation_idx on simulated_actions (conversation_id, claimed_at);
