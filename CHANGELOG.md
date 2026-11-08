# Changelog

## Unreleased

## 0.3.0 - 2026-11-08

Living documentation, agent context, and learning.

### Keep docs in step with code

- Track freshness per page. `sync` records content IDs of covered and linked files and
  fingerprints of cited line ranges. `status` reports `stale`, `review`, and `unsynced`
  pages, including changes that were already committed.
- Fingerprint the Python function or class around a cited line range by its syntax tree,
  so comments and formatting do not count. Other files use normalized text.
- Detect moved evidence and rewrite its line links with `fix-anchors`. The Claude stop
  hook does this automatically (`fixAnchors`), with no model.
- Warn when backticked paths, `name()` symbols, or `npm run` scripts in pages no longer exist.
- Check heading anchors, line anchors past the end of a file, and Mermaid diagram types.
- Count evidence links as coverage in `impact` and `status`.

### Give agents context cheaply

- Load a compact page map at Claude Code session start, or write it into `AGENTS.md`
  or another `contextFile` for any agent. Written blocks omit stale flags.
- Name the page that documents a file when the agent reads or edits it, once per page per session.
- Add a stop hook that reminds once per stale set, or with `autoUpdate: "auto"` asks the
  agent to run the isolated update. It also catches changes committed during the session.
- Make `update` model-invocable so agents can keep docs current; it still runs isolated.
- Setup reads only the configuration sections it needs, which lowers its cold load.

### Learn and measure

- Add `/archlens:learn` for questions, a guided tour, quizzes, and change walkthroughs.
- Add deterministic and model-based benchmarks, chart rendering, and a competitor review.

### Project

- Support Python 3.9, the macOS system Python.
- Publish `archlens-check` and `archlens-stale` pre-commit hooks, a CI recipe, and a project website.
- Lint pull request titles as Conventional Commits with the same types and scopes as the
  `commit-msg` hook. Add a commit template (`.gitmessage`) and document commit and PR conventions.
- Restructure the pull request template and add a documentation issue form and direct Discussions links.
- Attest build provenance for release archives. Verify with `gh attestation verify`.
- Add dependency review, path and branch based PR labels, labels as code, release-note categories, and `CITATION.cff`.
- Use `type(deps)` Dependabot commit prefixes and a 7-day cooldown for version updates.
- Add CI job timeouts and stop persisting checkout credentials in workflows.
- Let the maintainer push to `main` directly. Everyone else needs a reviewed pull request,
  and nobody can force-push or delete `main`.
- Add a Code of Conduct, support and governance guides, issue and pull request templates, and CODEOWNERS.
- Add pre-commit hooks for formatting, secrets, workflows, commit messages, portable-skill drift,
  prompt budgets, and handbooks. CI runs them too.
- Add versioned rulesets for `main` and release tags, a single `CI passed` required check,
  Dependabot, and OpenSSF Scorecard.
- Include community files in release archives.

## 0.2.0 - 2026-11-06

- Add one portable Agent Skill for setup, update, check, explanation, and decisions.
- Generate its resources from the native Claude plugin and check for distribution drift.
- Support a shared cross-agent user configuration with the existing Claude location as a fallback.
- Test isolated project and global installations with ten skills CLI adapters.
- Add portable prompt budgets and include the skill in release archives.

Portable host discovery, context isolation, and model behavior vary by agent.
Installer tests do not establish end-to-end model reliability.

## 0.1.1 - 2026-11-06

- Include the MIT notice inside the plugin so it remains present when the host copies only that directory.
- Add distribution tests for the installed license and release archive.

## 0.1.0 - 2026-11-06

- Five manual Claude Code commands for setup, update, check, explanation, and decisions.
- User and project preferences, evidence rules, and a JSON document map.
- Optional dependency-free Python checks and Git change-impact reports.
- Bounded summaries, conditional prompt loading, and prompt-size regression tests.
- Working order example with a six-page handbook.
- Cross-platform tests, Mermaid rendering checks, and reproducible release packaging.

Limits: model-task token savings and semantic output quality have not been benchmarked.
The checker does not certify STE compliance or prove architecture accuracy.
