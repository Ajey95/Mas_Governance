# MASGuardEval Python package

MASGuardEval evaluates guarded and baseline agent tool calls in an isolated
software workspace. The package provides a Python SDK and a `masguardeval`
command. The default adapter is scripted; its outputs are reference examples,
not empirical safety estimates.

Install with `python -m pip install masguardeval` (or use
`python -m pip install ./backend` from a checkout). See the
[SDK guide](https://masguardeval.onrender.com/docs/sdk/),
[integrations](https://masguardeval.onrender.com/docs/integrations/),
and [runnable examples](https://github.com/Ajey95/Mas_Governance/tree/main/examples)
for the public API and integrations. The command accepts caller-supplied
scenario datasets; run `masguardeval --help` after installation.

The Python package and code under `backend/` are licensed under the
[MIT License](https://github.com/Ajey95/Mas_Governance/blob/main/backend/LICENSE).
The paper, study datasets, reviewer records, and other repository materials
are outside this package license.
