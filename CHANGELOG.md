# Changelog

## Unreleased

Tested on a real 50,000-line monorepo (FastAPI, React/TypeScript, Modal) with 6,000 lines of existing docs.

### Fix existing docs, not just new ones

- Map existing documents in place with `../` page paths, such as `../ARCHITECTURE.md`.
  Archlens checks their links and references, tracks their freshness, and lists them in the agent map.
- `/archlens:setup adopt` (the default when docs exist) maps existing docs and decision records,
  fixes statements the code contradicts with minimal edits, and adds pages only for gaps.
  `/archlens:setup new` keeps the earlier behavior: a separate handbook that links existing docs.
- `update` verifies named and `needs-review` pages even when they are fresh, and keeps the
  structure of mapped existing documents.
- New decisions follow the project's existing decision folder and numbering.

### Update docs once per commit

- Add `autoUpdate: "commit"`, now the default. Before Claude runs `git commit`, a new PreToolUse
  hook holds the commit once while it would leave pages stale. The agent runs the isolated update,
  and the docs land in the same commit as the code. `remind` and `auto` still work.
- The `AGENTS.md` block tells other agents to update stale pages before they commit code.

### Fewer false alarms, more precise drift

- Fingerprint functions and classes in C-family files (JavaScript, TypeScript, Go, Rust, Java,
  C#, C/C++, Swift, PHP, Dart, and others) with a comment- and string-aware brace reader.
  Comment edits are ignored and moved functions are followed, as in Python.
- A line range inside a larger function tracks only its own lines. One changed rule in a
  40-line function no longer flags every citation inside it.
- A whole-file link to code goes stale only when the file's declared names change; body
  edits mark the page for review. A comment-only edit no longer makes a glossary stale.
- `check` reports style heuristics as one `info` note per page that never fails `--strict`,
  and sorts errors first. On the trial repository, 407 semicolon warnings had hidden one real broken anchor.
- `check` skips Git-ignored paths, extension-less names that never existed (such as `tools/list`),
  and paths named in accepted decision records.

### Give agents better context

- Add `cite`, which prints link-ready line ranges for symbols, so pages cite exact evidence.
- `check` warns when a line range cuts off a function's first or last code line by one or two lines.
- A comment added inside a function now moves the citations inside it, so `fix-anchors` rewrites them;
  before, those links silently pointed one line off.
- Map summaries take priority over coverage lists when the map is over budget.
- Map summaries come from a page's "Summary" section when it has one.
- When the map is over budget, it drops detail page by page in reading order, instead of
  removing every summary at once.
- Setup and update instructions now say how to cite code, including the line that sets each limit.
  The handbook index is named `README.md` so code hosts show it for the folder.

## 0.3.0 - 2026-11-08

Living documentation, agent context, and learning.

### Keep docs in step with code

- Track freshness per page. `sync` records content IDs of covered and linked files and
  fingerprints of cited line ranges. `status` reports `stale`, `review`, and `unsynced`
  pages, including changes that were already committed.
- Fingerprint the Python function or class around a cited line range by its syntax tree,
  so comments and formatting do not count. Other files use normalized text.
  Fingerprints are identical on Python 3.9 through 3.14.
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
