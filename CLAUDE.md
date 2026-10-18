# OpenTimelineIO Library

A Griptape Nodes library that reads a Fountain script, builds an OpenTimelineIO timeline from it, and (later) shows the timeline in a widget for timing adjustments.

## Structure

- `otio_nodes/fountain.py` parses Fountain text into plain dicts, keeping source line numbers. No engine imports.
- `griptape-nodes-library.json` is the node and widget manifest. Register new nodes and widgets here.
- `tests/` holds the pytest suite. Keep every module that does real work free of engine imports so it can be tested without the engine.

## Commands

- `make install/dev` installs dev dependencies.
- `make check` runs ruff format, ruff lint, pyright and JSON validation.
- `make deps/sync` copies `pip_dependencies` from `pyproject.toml` into the library JSON. Run it after changing dependencies.

## Rules

- Load the `griptape-nodes-widget-dev` skill (in `griptape-nodes-library-annotate/.claude/skills/`) before writing widget code.
- OTIO metadata goes under one namespaced key, never a custom schema.
- OTIO times are whole frames at the chosen rate.
- After editing any widget file, run `make widget/stamp` (or `make fix`). The engine only versions the widget's entry file, so imports of the other widget files carry a hash too. Without it the editor can mix old and new files and fail with "does not provide an export named ...". `make check` fails when the stamps are stale.
- Run `make check` before calling a task done.
