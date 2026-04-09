# CLAUDE.md — odoo-configurator

## Project overview

`odoo-configurator` is a Python CLI that configures Odoo databases from YAML files. It installs modules, writes settings, creates/updates records, runs CSV imports, and executes Python scripts — driven by a declarative config.

The tool follows a three-phase pipeline: **Loader** → **Planner** → **Executor**.

## Repository layout

```
src/odoo_configurator/
  __main__.py      CLI entry point (argparse, target loading, dispatch)
  loader.py        YAML loading, includes: merge, sequence: for DI mode
  planner.py       config dict → list[Operation]
  executor.py      list[Operation] + Context → Odoo calls + plugin loading
  operations.py    All Operation dataclasses (the YAML directive vocabulary)
  context.py       Context dataclass (dependency container for executor/plugins)
  client.py        Thin s6r_odoo wrapper + image caching helpers
  evaluator.py     get_* expression eval namespace and resolve functions
  secrets.py       env:// URI resolution, .env loading
  utils.py         File path resolution (resolve_path, resolve_dir)
  logging.py       Coloured logging setup
  sql.py           SQL connection helpers (PostgreSQL, MySQL, MSSQL)

tests/
  conftest.py           Shared fixtures and s6r_odoo import stub
  test_client.py
  test_evaluator.py
  test_executor.py
  test_loader.py
  test_planner.py
  test_secrets.py
  test_utils.py
```

## Dev setup

```bash
uv sync --extra dev   # or: pip install -e ".[dev]"
pytest                # run all tests (137 tests, ~0.3s, no network)
```

## Running tests

```bash
pytest tests/                  # full suite
pytest tests/test_planner.py   # single file
pytest -k "test_upsert"        # by name pattern
```

Tests never touch a real Odoo server. `s6r_odoo` is stubbed in `conftest.py` via `sys.modules` because it imports `xlrd` at module level.

## How to add a new YAML directive

Every YAML directive maps to exactly one Operation type. Adding one requires three changes:

1. **`operations.py`** — add a `@dataclass` for the new operation
2. **`planner.py:_emit_section()`** — add a clause that emits the operation from the config dict
3. **`executor.py:_dispatch()`** — add a `case` and a `_execute_*` function
4. **`tests/test_planner.py`** — add tests for the planner clause
5. **`tests/test_executor.py`** — add tests for the executor function

## Code conventions

- All new files use `from __future__ import annotations` and `# Copyright 2025 Scalizer` header.
- Python minimum version is **3.10** (`match` statements are used in the executor).
- No `OrderedDict` — PyYAML returns plain dicts, all isinstance checks use `dict`.
- `__builtins__: {}` is set in the eval namespace to prevent arbitrary code execution from YAML.
- Plugin functions loaded via `handler: file.py::function` must have signature `func(ctx, params)` or `func(ctx, file_path, model, params)` for CSV handlers.
- `ctx.client.odoo` is the raw `s6r_odoo.OdooConnection` — use it for ORM calls not covered by the `OdooClient` wrapper.

## Secrets

Use `env://VAR_NAME` in any credential field. A `.env` file at the project root is loaded automatically (via `python-dotenv`). Never commit plain passwords.

## Optional dependencies

SQL drivers and Slack are optional extras — do not add them to core `dependencies` in `pyproject.toml`. Install with `pip install "odoo-configurator[postgresql,slack]"`.

## README rule

**After every code change, check whether `README.md` still accurately reflects the feature.** If the change adds, removes, or modifies a YAML directive, CLI flag, expression function, or plugin convention, update the README or propose the update to the user before finishing.

The README is the only user-facing documentation. It must stay in sync.
