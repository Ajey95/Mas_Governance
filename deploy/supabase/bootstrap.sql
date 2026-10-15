-- Run once on a new Supabase project through its SQL editor or a reviewed migration.
-- This application writes through a server-side PostgreSQL connection. The study
-- trace schema is deliberately absent from Supabase's exposed Data API schemas.
create schema if not exists extensions;
create extension if not exists vector with schema extensions;
create schema if not exists masguardeval;

revoke all on schema masguardeval from public, anon, authenticated;

create table if not exists masguardeval.masguardeval_runs (
  trace_id text primary key,
  scenario_id text not null,
  mode text not null,
  adapter text not null,
  scenario_json jsonb not null,
  started_at timestamptz not null,
  completed_at timestamptz,
  elapsed_ms double precision,
  blocked boolean not null default false,
  stop_reason text,
  final_response text not null default ''
);
create table if not exists masguardeval.masguardeval_spans (
  sequence bigint generated always as identity primary key,
  trace_id text not null references masguardeval.masguardeval_runs(trace_id),
  payload_json jsonb not null
);
create index if not exists idx_mge_runs_started on masguardeval.masguardeval_runs(started_at desc);
create index if not exists idx_mge_spans_trace on masguardeval.masguardeval_spans(trace_id, sequence);
alter table masguardeval.masguardeval_runs enable row level security;
alter table masguardeval.masguardeval_spans enable row level security;
revoke all on all tables in schema masguardeval from anon, authenticated;
alter default privileges in schema masguardeval revoke all on tables from anon, authenticated;

-- PgVectorScenarioIndex creates the vector table at the configured dimensions
-- on first use. It also enables RLS with no client-facing policies.
