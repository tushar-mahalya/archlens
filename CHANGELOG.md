# Changelog

## 0.5.0 - 2026-11-11

Found by measuring 0.4.0 on a real monorepo handbook (22 pages, 81 line-range citations) with three
new model-free benchmarks. Numbers and method are in [benchmarks](docs/benchmarks.md).

### No false alarms on harmless edits

- A mutation benchmark makes one edit with a known right answer per citation. On the trial handbook,
  0.4.0 flagged 52 of 420 harmless edits (12.4%) and missed 4 of 217 real changes. 0.5.0 flags 0 of 420
  and detects 226 of 226. On every function in that codebase it is 3,611 of 3,613 detected.
- Every cited range now has a fingerprint of its content lines, without comments and blank lines.
  Before, a range that ended one blank line after a function, covered two functions, or covered
  module-level constants or YAML used a hash of the raw text, so a new comment made the page stale.
- A cited Python sub-range keeps its indentation. A statement that moves out of its `if` block is a change.
- `sync --fresh` records fresh pages again. Run it once after you upgrade, to move fingerprints to
  the new format. Records from 0.4.0 still compare correctly until then.

### Hooks cost half as much, or less

- Claude Code starts a process for every hook. A small entry, `scripts/hook.py`, now answers the
  common cases first. A Bash call that is not a commit costs 14 ms, down from 36 ms. So does every
  tool call in a project without a handbook.
- `status` skips the parse of a cited file whose content is unchanged. Session start, turn end, and
  the commit gate take about 100 ms on the trial monorepo, down from about 215 ms.
- The file pointer keeps an index of page links and answers a repeated file at once: 34 ms, down from 55 ms.

### Fixes from the trial review

The trial pages were accurate. Their placement and metadata habits were the cost to a reader.

### One home for each kind of document

- `check` warns when a handbook decision record sits beside a project decision folder, such as
  `docs/adr/` (`decision-split`). New decisions belong in the project's folder and numbering.
- `check` warns when nothing outside the handbook links to it while the project has a `README.md`
  (`unlinked-handbook`). Before, only the Claude session hook could find the handbook.
- Setup fixes check warnings, not only errors. In adopt mode it extends or links a view that an
  existing document already shows instead of redrawing it, and links the index from the README.
- `decide` names the adopted decision folder explicitly.

### Keep metadata out of prose

- `check` notes commit IDs in handbook prose (`prose-metadata`) and table columns that say unknown
  in every row (`unknown-column`). Both are `info` and never fail `--strict`.
- Templates and the contract say that `map.json` holds the verified commit, owner, and review state,
  and that pages describe the system, not the documentation session. Edits and reverts go in the handoff.
- "Inferred" now means that no linked source states the claim. A rule read in code is observed.

### Read one section, not a whole page

- Add `query`: ranked sections for words, the sections that cite a file, a page outline, one diagram
  with its text equivalent, or one step-table row. Every result has a line range. No model.
- The file pointer names up to two sections that cite the file, with line ranges.
- A diagram is the index to a flow: read it first, then ask for `--step 7` or `--row <unit>`.
  `learn` tours show the diagram first, and `explain` reuses sections that already trace a scenario.
- Measured without a model: on a trial monorepo with 220 KB of mapped documents, the top three
  sections are a fifth of the bytes of their whole pages for 13 points less key-term recall. On this
  repository's small handbook the gain is about a quarter with 11 points less recall, so the session map
  names `query` only from eight pages up. See [benchmarks](docs/benchmarks.md).

### One deterministic gate per commit

- Add `precommit` and the `archlens` pre-commit hook. It rewrites moved links, fails on structural
  errors, and fails when a staged file changes code that a page cites. Pages that were already stale
  only produce a note, so an old repository can adopt the hook. `--stale warn` reports without failing.

### Measured style and diagram checks

- `check` reports `stylePassRate` for handbook pages: complete sentences that pass length, semicolon,
  by-passive, and wordy-phrase rules. `--style` fails below `styleTarget`, which no command enforced
  before. The rate is a mechanical floor, not an STE score.
- `maxDiagramNodes` was validated but never used. `check` now counts flowchart nodes (`diagram-density`).
- `check` compares a step table with its numbered sequence diagram (`sequence-steps`).
- In adopted documents, presentation advice is a note, not a warning. Archlens does not restyle
  documents it did not write, so `--strict` no longer fails on them.

### Context map

- Index and glossary pages no longer spend map bytes on coverage patterns that span the project.
- When page summaries do not all fit, a folder of four or more decision records becomes one line.
  On the trial monorepo, every working page now shows its summary inside the same 3,000 bytes.

### Fewer false alarms

- `decision-split` warns only for the folder with fewer records. `unlinked-handbook` also accepts a
  parent `README.md` or `index.md`, and a root file that names the handbook folder.
- `prose-metadata` needs a digit in the commit ID.

## 0.4.0 - 2026-11-10

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
- A whole-file link to code goes stale only when a declared name in the file is removed or renamed;
  added names and body edits mark the page for review. A comment-only edit no longer makes a glossary stale.
- An edit to a linked document (Markdown and similar) marks a page for review, not stale, so fixing
  one existing doc no longer flags every page that links it. Deleting a linked file now makes a page stale;
  before, its broken link only marked the page for review.
- `check` reports style heuristics as one `info` note per page that never fails `--strict`,
  and sorts errors first. On the trial repository, 407 semicolon warnings had hidden one real broken anchor.
- `check` skips Git-ignored paths, extension-less names that never existed (such as `tools/list`),
  and paths named in accepted decision records.

### Give agents better context

- `fix-anchors` and the hooks rewrite links to files that Git reports as renamed, with no model.
  When a cited function disappears, `status` names a likely rename (`now \`is_authorized\`?`).
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

### Website

- The project website moved to https://archlens-docs.pages.dev/ on Cloudflare Pages and deploys on
  every push that changes `site/`. The GitHub Pages address is retired.

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
