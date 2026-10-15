# Official site and local workbench

The public Render service at `https://masguardeval.onrender.com` serves only
the MASGuardEval landing page, documentation, tutorials, examples, and method
overview. `masguardeval.official_site:app` has no evaluation, trace, login,
approval, or LangGraph execution routes. `Dockerfile` copies only the Python
package and `website/`; it does not ship the dashboard build, datasets,
reports, or Supabase credentials.

Run the evaluation workbench locally:

```powershell
python -m pip install -e "backend[langgraph]"
python scripts/start_local_dashboard.py
```

Open `http://127.0.0.1:8000`. The launcher builds the React frontend and
serves it and the API on loopback. It clears inherited hosted database and
authentication flags, uses a local SQLite trace store, and does not contact
Supabase for normal dashboard use. The optional model-driven LangGraph example
uses local Ollama and fictional mock tools:

```powershell
python examples/langgraph_react.py --model YOUR_INSTALLED_MODEL
```

The former Render/Supabase private preview and its operational verification
are retained in [the historical deployment record](DEPLOY_RENDER_SUPABASE.md).
Its Supabase project and tables are not required to use the current local
workbench or public site.

## Deployment checks

After a public-site deployment, `GET /health` must identify
`official_site`; `/`, `/docs/`, `/tutorials/`, `/examples/`, and `/method/`
must return 200. `/dashboard`, `/runs`, `/scenarios`, `/user-login`, and
`/openapi.json` must return 404. The local workbench has the opposite role:
it serves `/dashboard`, `/runs`, and the trace routes on `127.0.0.1`.
