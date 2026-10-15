# Render and Supabase deployment

This is the deployed path for MASGuardEval. [Render](https://masguardeval.onrender.com) runs the React dashboard and FastAPI service in one Free-plan Docker web service in Singapore. Supabase hosts PostgreSQL, pgvector, and user authentication in Singapore. The application connects to the private `masguardeval` schema through a server-side database URL; no database password or provider API key belongs in Git or browser code.

## Prepared files

- [`render.yaml`](../render.yaml) defines the Render web service, health check, and required secret prompts.
- [`Dockerfile`](../Dockerfile) builds the frontend and Python API into one image, including the LangGraph runtime adapter.
- [`deploy/supabase/bootstrap.sql`](../deploy/supabase/bootstrap.sql) creates the private trace schema and pgvector extension.
- [`supabase/migrations/20261015085327_masguardeval_bootstrap.sql`](../supabase/migrations/20261015085327_masguardeval_bootstrap.sql) is the CLI-managed copy of that schema, aligned with the hosted migration history.
- [`supabase/migrations/20261015120855_trace_ownership.sql`](../supabase/migrations/20261015120855_trace_ownership.sql) assigns existing preview traces to `research-preview` and adds an indexed owner for new authenticated runs. The migration was applied to the hosted project on 2026-10-15.
- `masguardeval.web:app` serves the frontend and API from one origin and requires a site token when the Render preview flag is enabled.
- With `MASGUARDEVAL_REQUIRE_USER_AUTH=1`, users sign in through Supabase Auth after the research preview gate. The API validates each session against the Auth server and scopes saved traces, graphs, findings, and approval requests to the authenticated user. Tokens stay in Secure, HttpOnly cookies; refresh rotates them through Supabase Auth.

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

The site token remains a **shared preview gate**. The separate Supabase Auth account identifies each user, and the backend binds new trace rows to that Auth user ID. Four traces created before the ownership migration remain under `research-preview` and are not visible through user-scoped routes. The database schema stays private, with no `anon` or `authenticated` Data API grants; the backend enforces owner filters. Keep the site token private and do not use real customer secrets or private external tool traces in the reference workflow.

The Supabase Auth Site URL and redirect allowlist are set to `https://masguardeval.onrender.com` using a CLI config diff/push. Hosted email confirmation is enabled. Before inviting arbitrary external users, configure and test a suitable SMTP sender and account recovery flow; the current Free-plan email service has not been validated for general onboarding.

The paper study remains separate from deployment. A successful service smoke does not validate the metrics, model outcomes, human agreement, or the scenario dataset.
