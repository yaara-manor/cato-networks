-- Agent runtime state. Re-applied on every start by apply_schema, hence
-- "if not exists" everywhere. These tables are deliberately EXCLUDED from
-- db/seed.dump (pg_restore --clean would otherwise wipe live conversations on
-- every boot) and carry no foreign keys into accounts/tickets/KB tables.
-- Enum-like text columns are validated by Pydantic StrEnums, not CHECKs.

create table if not exists conversations (
    id uuid primary key,
    account_id text null,
    contact_email text null,
    customer_tier text not null,
    active_site_id text null,
    stage text not null,
    guard_history jsonb not null default '{}',
    last_turn int not null default 0,
    last_seq int not null default 0,
    state jsonb not null default '{"version": 1}',
    created_at timestamptz not null,
    updated_at timestamptz not null
);
create index if not exists conversations_account_idx on conversations (account_id);

create table if not exists messages (
    id uuid primary key,
    conversation_id uuid not null references conversations on delete restrict,
    turn int not null,
    sender text not null,
    content text not null,
    citations jsonb not null default '[]',
    telemetry_evidence jsonb not null default '[]',
    created_at timestamptz not null
);
create index if not exists messages_conversation_turn_idx on messages (conversation_id, turn);

create table if not exists traces (
    id uuid primary key,
    conversation_id uuid not null references conversations on delete restrict,
    message_id uuid null references messages on delete restrict,
    turn int not null,
    seq int not null,
    agent_role text not null,
    parent_trace_id uuid null references traces on delete restrict,
    input jsonb not null,
    output jsonb null,
    model_messages jsonb null,
    status text not null,
    error text null,
    latency_ms int not null,
    prompt_tokens int not null,
    completion_tokens int not null,
    cost_usd numeric null,
    started_at timestamptz not null,
    created_at timestamptz not null,
    unique (conversation_id, seq)
);
create index if not exists traces_conversation_turn_idx on traces (conversation_id, turn);

create table if not exists tool_calls (
    id uuid primary key,
    trace_id uuid not null references traces on delete restrict,
    conversation_id uuid not null references conversations on delete restrict,
    seq int not null,
    tool_name text not null,
    arguments jsonb not null,
    status text not null,
    result jsonb not null,
    latency_ms int not null,
    created_at timestamptz not null,
    unique (trace_id, seq)
);
create index if not exists tool_calls_conversation_tool_status_idx
    on tool_calls (conversation_id, tool_name, status);

create table if not exists approvals (
    id uuid primary key,
    conversation_id uuid not null references conversations on delete restrict,
    message_id uuid not null references messages on delete restrict,
    action_type text not null,
    payload jsonb not null,
    status text not null,
    idempotency_key text not null,
    reviewer_notes text null,
    edited_payload jsonb null,
    requested_at timestamptz not null,
    resolved_at timestamptz null,
    unique (conversation_id, idempotency_key)
);
create index if not exists approvals_pending_idx on approvals (status) where status = 'PENDING';
