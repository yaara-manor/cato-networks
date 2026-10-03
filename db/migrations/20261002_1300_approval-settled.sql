-- Reviewer-resolution follow-up: settled_at marks "executed + customer notified".
alter table approvals add column if not exists settled_at timestamptz;
alter table approvals add column if not exists customer_reason text;
create index if not exists approvals_unsettled_idx on approvals (resolved_at)
    where status <> 'PENDING' and settled_at is null;
