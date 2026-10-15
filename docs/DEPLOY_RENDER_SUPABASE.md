# Render and Supabase deployment

This is the selected deployment path for MASGuardEval. Render runs the React dashboard and FastAPI service in one Docker web service in Singapore. Supabase hosts PostgreSQL and pgvector in Singapore. The application connects to the private `masguardeval` schema through a server-side database URL; no database password or provider API key belongs in Git or browser code.

## Prepared files

- [`render.yaml`](../render.yaml) defines the Render web service, health check, and required secret prompts.
- [`Dockerfile`](../Dockerfile) builds the frontend and Python API into one image, including the LangGraph runtime adapter.
- [`deploy/supabase/bootstrap.sql`](../deploy/supabase/bootstrap.sql) creates the private trace schema and pgvector extension.
- [`supabase/migrations/20261015085327_masguardeval_bootstrap.sql`](../supabase/migrations/20261015085327_masguardeval_bootstrap.sql) is the CLI-managed copy of that schema, aligned with the hosted migration history.
- `masguardeval.web:app` serves the frontend and API from one origin and requires a site token when the Render preview flag is enabled.

## Provisioned Supabase project

The Supabase CLI created [MASGuardEval](https://supabase.com/dashboard/project/ngwklaaqxqxttiswcnje) on 2026-10-15 in Ajey95's Free-plan organization (`ftppuogtdpvbepymzjsx`), region `ap-southeast-1`. Project ref: `ngwklaaqxqxttiswcnje`. The CLI is linked locally, and the generated database password is stored as a Windows user-bound encrypted file outside this repository at `C:\Users\AJEYA\.codex\secrets\masguardeval-supabase-db-password.dpapi`.

This machine cannot establish TCP connections to the Supabase pooler on ports 5432 or 6543. `supabase db push --linked --dry-run` failed with `ECONNREFUSED`, so the exact reviewed migration was applied through the connected Supabase SQL service. Hosted migration history records version `20261015085327`; the local CLI migration file uses the same version. Live SQL confirmed PostgreSQL 17.11, pgvector 0.8.2 in `extensions`, two private trace tables with RLS enabled, and no `anon` or `authenticated` read access. A pgvector cosine-distance query returned the expected value. These are database checks; the application-to-database route still needs a deployed service trial.

The Supabase security advisor reports two informational [`rls_enabled_no_policy`](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy) notices. This is intentional: the private schema has no client-facing policies. The performance advisor reports two [`unused_index`](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index) notices because the tables are empty.

## Provisioning order

1. Set `MASGUARDEVAL_DATABASE_URL` in Render to a session-pooler PostgreSQL connection string from the project. Set `MASGUARDEVAL_SITE_TOKEN` to a strong private-preview token. The Blueprint refuses to start without these values. Keep any LLM and LangSmith keys in Render secrets only if their live integrations are enabled.
2. Connect the reviewed Git repository and deploy the Render Blueprint. Verify `/health`, the login gate, dashboard, one streamed run, saved spans, graph, and findings through the deployed URL. Redeploy the service and verify that the trace still exists in Supabase.
3. Run `POST /langgraph/reference-run` through the authenticated preview, then read its saved trace and graph. This exercises LangGraph node/route observation and the private-schema PostgreSQL checkpointer on the Render-to-Supabase path.

The site token is a **shared preview gate**. It prevents anonymous access but does not identify separate users or isolate their traces. Keep the deployment private to the research team until per-user authentication and tenant isolation are implemented and tested. Do not use real customer secrets, emails, or private tool traces in the preview.

The paper study remains separate from deployment. A successful service smoke does not validate the metrics, model outcomes, human agreement, or the scenario dataset.
