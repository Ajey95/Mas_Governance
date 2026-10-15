# Render and Supabase deployment

This is the deployed path for MASGuardEval. [Render](https://masguardeval.onrender.com) runs the React dashboard and FastAPI service in one Free-plan Docker web service in Singapore. Supabase hosts PostgreSQL and pgvector in Singapore. The application connects to the private `masguardeval` schema through a server-side database URL; no database password or provider API key belongs in Git or browser code.

## Prepared files

- [`render.yaml`](../render.yaml) defines the Render web service, health check, and required secret prompts.
- [`Dockerfile`](../Dockerfile) builds the frontend and Python API into one image, including the LangGraph runtime adapter.
- [`deploy/supabase/bootstrap.sql`](../deploy/supabase/bootstrap.sql) creates the private trace schema and pgvector extension.
- [`supabase/migrations/20261015085327_masguardeval_bootstrap.sql`](../supabase/migrations/20261015085327_masguardeval_bootstrap.sql) is the CLI-managed copy of that schema, aligned with the hosted migration history.
- `masguardeval.web:app` serves the frontend and API from one origin and requires a site token when the Render preview flag is enabled.

## Provisioned Supabase project

The Supabase CLI created [MASGuardEval](https://supabase.com/dashboard/project/ngwklaaqxqxttiswcnje) on 2026-10-15 in Ajey95's Free-plan organization (`ftppuogtdpvbepymzjsx`), region `ap-southeast-1`. Project ref: `ngwklaaqxqxttiswcnje`. The CLI is linked locally, and the generated database password is stored as a Windows user-bound encrypted file outside this repository at `C:\Users\AJEYA\.codex\secrets\masguardeval-supabase-db-password.dpapi`.

This machine cannot establish TCP connections to the Supabase pooler on ports 5432 or 6543. `supabase db push --linked --dry-run` failed with `ECONNREFUSED`, so the exact reviewed migration was applied through the connected Supabase SQL service. Hosted migration history records version `20261015085327`; the local CLI migration file uses the same version. Live SQL confirmed PostgreSQL 17.11, pgvector 0.8.2 in `extensions`, and a successful vector cosine query. The deployed application-to-database route is verified below.

The Supabase security advisor reports six informational [`rls_enabled_no_policy`](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy) notices for private tables. This is intentional: the schema has no client-facing policies. The performance advisor reports three informational [`unused_index`](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index) notices for new checkpoint indexes. No higher-level advisor issue was returned on 2026-10-15.

## Live deployment verification, 2026-10-15

- Render service `srv-db8bjbcs728c738simig` deployed commit `1ba2e61` on the Free plan. `/health` returned 200; unauthenticated `/runs` returned 401; the private preview login returned 204; the authenticated dashboard returned 200.
- An authenticated guarded SSE run of `auth_001` saved trace `2b0c984d-68a5-4313-9ad5-b7bf653eb141` with 14 spans. Its saved trace, graph, and findings routes returned successfully. The same trace remained readable after the next Render revision, confirming storage outside the instance.
- `POST /langgraph/reference-run` ran a fictional, bounded LangGraph tool workflow on Render. It saved trace `f7ad9704-e535-4d30-9997-9d780588cf5a` with 22 spans, seven graph/agent/tool nodes, four observed graph edges, and checkpoint `1f1c88d3-e0a6-6e17-8002-4d3417d59f0a`. Both the trace and graph were read back through authenticated API routes.
- `POST /langgraph/checkpoint-probe` paused thread `checkpoint-probe-9fa971e4-3bd1-4f99-9a34-03172ba7e628`, closed its checkpointer connection, reopened a new one, and resumed with fixed fictional data. The paused trace `5bc8b1b6-93e4-4963-abf6-5368775e22d9` and resumed trace `fe9568b1-6e1d-4c21-bc5b-f8b29d0fb892` were both retrieved through authenticated routes. Supabase SQL found three persisted checkpoint steps for that thread.
- Supabase SQL found four checkpoint rows and the matching reference trace. All six tables in the private `masguardeval` schema have RLS enabled and grant neither `anon` nor `authenticated` role SELECT. LangGraph's checkpoint tables are package-managed by `PostgresSaver.setup()` on first use; the source migration prepares the private schema and trace tables.

This verifies a reference workflow and operational storage path. It does not establish real LLM study outcomes, multi-tenant authentication, or paper-grade metric validity.

## Provisioning order

1. Set `MASGUARDEVAL_DATABASE_URL` in Render to a session-pooler PostgreSQL connection string from the project. Set `MASGUARDEVAL_SITE_TOKEN` to a strong private-preview token. The Blueprint refuses to start without these values. Keep any LLM and LangSmith keys in Render secrets only if their live integrations are enabled.
2. Connect the reviewed Git repository and deploy the Render Blueprint. Verify `/health`, the login gate, dashboard, one streamed run, saved spans, graph, and findings through the deployed URL. Redeploy the service and verify that the trace still exists in Supabase.
3. Run `POST /langgraph/reference-run` through the authenticated preview, then read its saved trace and graph. Run `POST /langgraph/checkpoint-probe` to verify pause/resume across separate private-schema PostgreSQL checkpointer connections using fictional data.

The site token is a **shared preview gate**. It prevents anonymous access but does not identify separate users or isolate their traces. Keep the deployment private to the research team until per-user authentication and tenant isolation are implemented and tested. Do not use real customer secrets, emails, or private tool traces in the preview.

The paper study remains separate from deployment. A successful service smoke does not validate the metrics, model outcomes, human agreement, or the scenario dataset.
