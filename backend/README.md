# MASGuardEval Python package

MASGuardEval evaluates guarded and baseline agent tool calls in an isolated
software workspace. The package provides a Python SDK and a `masguardeval`
command. The default adapter is scripted; its outputs are reference examples,
not empirical safety estimates.

Install locally with `python -m pip install ./backend`. See the repository's
`docs/SDK.md`, `docs/INTEGRATIONS.md`, and `examples/README.md` for the public
API and runnable integrations. The command accepts caller-supplied scenario
datasets; run `masguardeval --help` after installation.

The Python package and code under `backend/` are licensed under the
[MIT License](LICENSE). The paper, study datasets, reviewer records, and other
repository materials are outside this package license.
