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

## Changelog

`CHANGELOG.md` follows [Keep a Changelog 2.0.0](https://keepachangelog.com/en/2.0.0/). Each version is the `library_version` in `griptape-nodes-library.json`. Its readers are artists using these nodes and the agents that build workflows with them.

**Add an entry for every user-facing change** - In the same PR, add a file to `changelog.d/` holding the entry. User-facing means anything a user notices after updating the library: a node added, removed, or renamed; a parameter, default, or output that differs; a provider model added or retired; a saved workflow that loads or runs differently. After adding one, tell the user so they can review the wording.

**One file per entry, named for its type** - Never edit `## [Unreleased]` in `CHANGELOG.md` directly; `make check/changelog` rejects it. Create `changelog.d/<type>-<slug>.md`, where `<type>` is one of `added`, `changed`, `deprecated`, `removed`, `fixed`, or `security`, and `<slug>` is a few lowercase words joined by hyphens. The whole file is the bullet, with no heading. `make changelog` prints `[Unreleased]` with these files folded in. `changelog.d/README.md` is the same contract for humans.

**Skip what users never see** - Refactors, tests, CI, docs-only changes, and dev dependency bumps get no entry. Neither does a fix for a bug that never shipped in a version: edit or delete the entry that introduced it.

**Describe the result, not the code** - Name the node and parameter in backticks or by their editor label, say what the user sees now, present tense, one or two sentences. `Fixed` if the old behavior was a bug, `Changed` if it was intentional. Link the GitHub issue on its own last line. Leave out PR numbers and `@handles`. Wrap at about 100 characters, continuation lines indented two spaces.

**Mark breaking changes** - A change that makes a saved workflow stop working, or give a different result, without edits starts with `**Breaking:**`. Say what breaks and what to do about it.

**Leave `CHANGELOG.md` to the version bump** - Do not add version headings or link definitions. `make version/patch`, `make version/minor`, `make version/major`, and `make version/set` fold the `changelog.d/` entries into the new version section and delete them. Fixing a mistake in a released entry is fine. After a patch release from a `release/` branch, `make changelog/backport v=<version>` on a branch off `main` brings that section back.
