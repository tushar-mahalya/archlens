# AGENTS.md

Guidance for AI coding agents working in this repository. Humans: see [CONTRIBUTING.md](CONTRIBUTING.md).

## What this is

Archlens keeps an architecture handbook (`docs/architecture`) in step with the code. It ships as a
Claude Code plugin, a portable Agent Skill, and a local checker. The checker,
`plugins/archlens/scripts/archlens.py`, uses only the Python standard library and supports Python 3.9+.
It makes no model calls and no network calls. Node is for development tooling only.

## Setup

```text
uv tool install pre-commit      # or: pipx install pre-commit
pre-commit install              # pre-commit, commit-msg, and pre-push hooks
npm ci                          # only for diagram and skill-installer checks; Node 22.20+
```

## Checks to run before you say a change is done

```text
pre-commit run --all-files                    # CI runs the same hooks
python -m unittest discover -s tests          # tests run offline
python tools/prompt_budget.py                 # loaded-instruction budgets
python tools/sync_portable.py --check         # portable skill matches the plugin
python plugins/archlens/scripts/archlens.py check --root . --strict
python plugins/archlens/scripts/archlens.py check --root examples/order-service --strict
python plugins/archlens/scripts/archlens.py status --root . --fail-on-stale
npm run test:diagrams && npm run test:skills  # after diagram or installer changes
```

The pre-commit hooks include ruff (lint only, no formatter), typos, zizmor, actionlint, and gitleaks.
There is no separate type checker. Fix findings; do not silence a check without a short reason beside it.

## Layout

- `plugins/archlens/`: the native plugin and the source of truth. `scripts/archlens.py` is the
  checker, `scripts/hook.py` is the small hook entry, `skills/` holds the six workflows, and
  `references/` holds the shared references.
- `skills/archlens/`: the portable skill. `SKILL.md` is edited by hand. Everything else is generated.
- `tools/`: release packaging, `sync_portable.py`, `prompt_budget.py`, and benchmarks.
- `tests/`: unit tests (`unittest`) and the installer test (`test-skills-install.mjs`).
- `docs/`: user documentation. `docs/architecture/` is this project's own handbook.
- `examples/order-service/`: the example project. Its handbook is checked in CI.
- `site/`: the static website, deployed by `.github/workflows/cloudflare-pages.yml`.
- `.github/rulesets/`: branch and tag protection as code.

## Conventions

- Branch from `main` as `type/short-description`, for example `fix/config-precedence`.
- Commits and PR titles use Conventional Commits. Scopes: `plugin`, `skill`, `checker`, `docs`,
  `site`, `ci`, `deps`, `bench`. The subject is imperative, lowercase, with no final period, and
  at most 72 characters. The `commit-msg` hook enforces this.
- Add a line to the `Unreleased` section of `CHANGELOG.md` for any user-facing change.
- Contributors sign the [CLA](CLA.md) on their first PR. You cannot sign for them.
- Pin every GitHub Action to a full commit SHA with a version comment. Pin pre-commit hooks to a
  frozen SHA (`pre-commit autoupdate --freeze`). Give each workflow least-privilege `permissions:`.
- This repo documents itself with Archlens. After you change covered code, run `status`, review the
  affected pages, then `sync --page <ID>` for the pages you checked. Commit
  `docs/architecture/.archlens-state.json` with the change.
- Write in short, concrete sentences. No marketing words and no emoji.

## Rules for agents

- Do not commit or print secrets, tokens, or private data. Tests must not need the network.
- Do not edit generated files by hand: `skills/archlens/{scripts,references,workflows}`,
  `skills/archlens/defaults.json`, `skills/archlens/LICENSE`, `docs/architecture/.archlens-state.json`,
  and `dist/`. Change the source under `plugins/archlens/`, then run `python tools/sync_portable.py`
  or `archlens.py sync`.
- Keep the checker standard-library only. Do not add a Python dependency or a custom YAML parser.
- Keep loaded instructions small. Run `tools/prompt_budget.py` after you change any prompt text.
- Add a regression test for each bug fix. The test must fail without the fix, and its expected
  values must come from an independent source, not from the code under test.
- Do not add a `Co-Authored-By` trailer or a "Generated with" line unless the human asks for one.
- Do not open issues or pull requests, post comments, mention maintainers, push, or force-push
  unless the human asks. Do not change repository settings or rulesets.
- Keep changes small and focused. Do not reformat files or rename things you were not asked to change.
- If a check fails, fix the cause. Do not claim a change is done until the checks above pass.
