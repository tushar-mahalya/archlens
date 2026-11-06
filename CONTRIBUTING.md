# Contributing

Use Python 3.10+ for tests. The runtime checker uses only the standard library.

```text
python -m unittest discover -s tests -v
python tools/prompt_budget.py
python plugins/archlens/scripts/archlens.py check --root examples/order-service --strict
python plugins/archlens/scripts/archlens.py check --root . --strict
python tools/package_release.py
```

If Claude Code is available:

```text
claude plugin validate . --strict
claude plugin validate ./plugins/archlens --strict
```

For diagram and portable installer checks, use Node 22.20+:

```text
npm ci
npm run test:diagrams
npm run test:skills
```

Set `DISABLE_TELEMETRY=1` and `DO_NOT_TRACK=1` for isolated installer tests.
The tests use temporary project and home directories, not your personal agent settings.
Node dependencies are development-only for the plugin. The portable installer's
own CLI separately requires Node.

## Portable skill

The native Claude plugin is the source of truth for shared references, defaults,
the checker, and the five workflows. After changing one of those resources, run:

```text
python tools/sync_portable.py
python tools/sync_portable.py --check
python tools/prompt_budget.py
```

Commit the generated files under `skills/archlens` with the source changes.
Do not edit generated workflows or bundled resources independently.
Edit the portable router `skills/archlens/SKILL.md` directly when its routing changes.
The generator reports unexpected generated files instead of deleting them.

## Changes

- Keep command prompts small. Run the budget test after instruction changes.
- Add regression tests for config, path, report, or Git behavior.
- Do not add a custom YAML parser.
- Do not label heuristics as official STE compliance.
- Keep evidence-based claims separate from inference.
- Do not add hooks, MCP servers, nested agents, or automatic commands without a context-cost review.
- Update the relevant reference and user documentation.

## Release

1. Update the plugin, marketplace metadata, and development package versions together.
2. Add release notes.
3. Pass CI and review the [evaluation plan](docs/context-efficiency.md).
4. Run the package tool. It creates a deterministic, allowlisted ZIP and SHA-256 checksum.
5. Publish the release from a tested commit.

The release archive includes the marketplace, plugin, portable skill, docs, example, tests, and development scripts.
It excludes installed dependencies, temporary tools, and local configuration.
