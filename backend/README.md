# MASGuardEval Python package

MASGuardEval evaluates guarded and baseline agent tool calls in an isolated
software workspace. The package provides a Python SDK and a `masguardeval`
command. The default adapter is scripted; its outputs are reference examples,
not empirical safety estimates.

Install with `python -m pip install masguardeval` (or use
`python -m pip install ./backend` from a checkout). See the
[SDK guide](https://github.com/Ajey95/Mas_Governance/blob/v0.1.2/docs/SDK.md),
[integrations](https://github.com/Ajey95/Mas_Governance/blob/v0.1.2/docs/INTEGRATIONS.md),
and [runnable examples](https://github.com/Ajey95/Mas_Governance/blob/v0.1.2/examples/README.md)
for the public API and integrations. The command accepts caller-supplied
scenario datasets; run `masguardeval --help` after installation.

The Python package and code under `backend/` are licensed under the
[MIT License](https://github.com/Ajey95/Mas_Governance/blob/v0.1.2/backend/LICENSE).
The paper, study datasets, reviewer records, and other repository materials
are outside this package license.
