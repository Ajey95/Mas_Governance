"""Build and serve the evaluation dashboard on loopback without Vite dev mode."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--skip-build", action="store_true", help="Use an existing frontend/dist build")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1..65535")
    if args.skip_build and not (DIST / "index.html").is_file():
        parser.error("frontend/dist is missing; run without --skip-build")

    environment = os.environ.copy()
    # A local dashboard must never inherit the hosted database or account gates.
    for name in ("MASGUARDEVAL_DATABASE_URL", "MASGUARDEVAL_REQUIRE_DATABASE_URL"):
        environment.pop(name, None)
    environment.update({
        "MASGUARDEVAL_REQUIRE_SITE_AUTH": "0",
        "MASGUARDEVAL_REQUIRE_USER_AUTH": "0",
        "MASGUARDEVAL_FRONTEND_DIST": str(DIST),
        "MASGUARDEVAL_DATASET_PATH": str(ROOT / "datasets" / "golden_scenarios.json"),
        "MASGUARDEVAL_TRACE_DB": str(ROOT / "reports" / "runs.sqlite3"),
        "PYTHONPATH": str(ROOT / "backend") + os.pathsep + environment.get("PYTHONPATH", ""),
    })

    if not args.skip_build:
        npm = "npm.cmd" if os.name == "nt" else "npm"
        build_environment = environment.copy()
        build_environment["VITE_API_BASE"] = ""
        if not (FRONTEND / "node_modules").is_dir():
            subprocess.run([npm, "ci"], cwd=FRONTEND, env=build_environment, check=True)
        subprocess.run([npm, "run", "build"], cwd=FRONTEND, env=build_environment, check=True)

    print(f"Local dashboard: http://127.0.0.1:{args.port}", flush=True)
    subprocess.run([sys.executable, "-m", "uvicorn", "masguardeval.web:app",
                    "--host", "127.0.0.1", "--port", str(args.port)],
                   cwd=ROOT, env=environment, check=True)


if __name__ == "__main__":
    main()
