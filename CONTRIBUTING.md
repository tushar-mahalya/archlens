# Contributing

Thank you for helping improve Archlens. By taking part, you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md). For questions, use
[Discussions](https://github.com/tushar-mahalya/archlens/discussions) and see [SUPPORT.md](SUPPORT.md).

## Workflow

1. For a non-trivial change, open an issue or discussion first. See [GOVERNANCE.md](GOVERNANCE.md).
2. Fork the repository and create a branch from `main` named `type/short-description`,
   for example `fix/config-precedence`. The `feat/`, `fix/`, and `docs/` prefixes set a PR label.
3. Install the Git hooks (below) and make focused commits.
4. Write commit messages and the PR title as described in
   [Commit and pull request conventions](#commit-and-pull-request-conventions).
5. Open a pull request and complete the template. The `CI passed` check, a code owner approval,
   and resolved review threads are required. See [Repository rulesets](#repository-rulesets).
6. Pull requests are merged by squash (preferred) or rebase. `main` keeps a linear history.

## Commit and pull request conventions

Commits and PR titles use [Conventional Commits 1.0](https://www.conventionalcommits.org/en/v1.0.0/):

```text
type(scope)!: subject

body

footers
```

- **type** (required): `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`,
  `style`, or `revert`. `feat` and `fix` are user-facing; use `refactor`, `test`, or `chore` for
  changes that are not.
- **scope** (optional): `plugin`, `skill`, `checker`, `docs`, `site`, `ci`, `deps`, or `bench`.
  Leave it out when a change spans several areas.
- **`!`** marks a breaking change. Add a `BREAKING CHANGE:` footer that says how to migrate.
- **subject**: imperative mood ("add", not "added" or "adds"), lowercase first word, no final period.
  The whole first line is 72 characters or fewer.
- **body** (optional): explain what changed and why, not how. Separate it from the subject with a
  blank line and wrap it at 72 characters.
- **footers** (optional), one per line: `Closes #123`, `Refs #45`,
  `BREAKING CHANGE: <description>`, and `Co-authored-by: Name <email>`.

Examples:

```text
fix(checker): reject local links that escape the project root
feat(skill): add a guided tour to the learn workflow
docs: explain how to verify release attestations
ci(deps): bump the actions group with 3 updates
feat(checker)!: exit with code 2 on configuration errors

BREAKING CHANGE: scripts that treated every non-zero exit as "stale" must
check for exit code 1.
```

The `commit-msg` hook checks each commit, and the **PR title** check enforces the same rules on
pull requests. A squash merge turns the PR title into the commit subject on `main`,
so keep the title accurate when the scope of a PR changes.
To start each commit from the template in [.gitmessage](.gitmessage), run:

```text
git config commit.template .gitmessage
```

## Git hooks

The repository uses [pre-commit](https://pre-commit.com/). Hooks check formatting, line endings,
JSON and YAML, GitHub workflows, secrets (gitleaks), commit messages, portable-skill drift, prompt
budgets, and the handbooks. Unit tests run before each push.

```text
pipx install pre-commit        # or: uv tool install pre-commit, or: pip install pre-commit
pre-commit install             # installs pre-commit, commit-msg, and pre-push hooks
pre-commit run --all-files     # optional: check the whole tree
```

CI runs the same hooks, so a skipped hook still fails the pull request.
Update hook versions with `pre-commit autoupdate --freeze`. Dependabot also proposes updates.

## Tests

Use Python 3.9+ for tests. The runtime checker uses only the standard library.

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
the checker, and the six workflows. After changing one of those resources, run:

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
5. Push a `v<version>` tag on a tested commit. The release workflow runs CI, attests the ZIP's
   build provenance, and publishes the release. See [SECURITY.md](SECURITY.md#verify-a-release).

The release archive includes the marketplace, plugin, portable skill, docs, example, tests, and development scripts.
It excludes installed dependencies, temporary tools, and local configuration.

Release tags (`v*`) are protected: they cannot be moved or deleted after publication.
Publish a new patch version instead of replacing a release.

## Repository rulesets

Branch and tag protection is defined as code in [.github/rulesets](.github/rulesets):

- `main.json`: **contributors** change `main` only through a pull request that passes the
  `CI passed` check, has one code owner approval, has all review threads resolved, and is merged
  by squash or rebase (linear history). **The maintainer** (repository admin) may push directly
  to `main`, for example for releases and urgent fixes. CI still runs on those pushes.
- `main-integrity.json`: **nobody**, including administrators, can force-push to or delete `main`.
  This ruleset has no bypass.
- `release-tags.json` blocks moving or deleting `v*` tags. Administrators can bypass it for recovery.

Pull requests also run **Conventional PR title**, **Dependency review**, and the labeler.

A maintainer applies a changed definition with the GitHub CLI:

```text
gh api repos/tushar-mahalya/archlens/rulesets --method POST --input .github/rulesets/main.json
gh api repos/tushar-mahalya/archlens/rulesets/<id> --method PUT --input .github/rulesets/main.json
```

Use `POST` for a new ruleset and `PUT` with the existing ID (`gh api repos/tushar-mahalya/archlens/rulesets`) to update one.

## Keep this project's handbook fresh

This repository uses Archlens on itself. CI and the pre-push hook run
`status --fail-on-stale`, so a change to covered code fails until the affected
pages are reviewed. After you update or confirm those pages, record them:

```text
python plugins/archlens/scripts/archlens.py status --root .
python plugins/archlens/scripts/archlens.py sync --root . --page ARCH-RUNTIME
```

Sync only pages you checked against the new source. Commit
`docs/architecture/.archlens-state.json` with the change.
