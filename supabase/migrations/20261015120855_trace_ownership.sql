-- Existing private-preview traces remain assigned to the research preview.
-- New authenticated runs bind to a verified Supabase Auth user ID in the API.
alter table masguardeval.masguardeval_runs
  add column if not exists owner_id text not null default 'research-preview';

create index if not exists idx_mge_runs_owner_started
  on masguardeval.masguardeval_runs(owner_id, started_at desc);
