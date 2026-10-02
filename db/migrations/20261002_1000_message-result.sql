-- Full TurnResult of a completed turn, so an idempotent retry replays the same envelope.
-- Null on rows written before this column existed.
alter table messages add column if not exists result jsonb null;
