# Method and research

Use a small, linked handbook rather than one giant generated document.
Make the reader's question the unit of documentation.

## Combined approach

| Source | Contribution |
|---|---|
| [arc42](https://arc42.org/overview) | Scope, structure, runtime, deployment, quality, decisions, risks |
| [C4](https://c4model.com/diagrams) | Levels of structural detail; use only the levels that add value |
| [MADR](https://adr.github.io/madr/) | Significant decisions, options, drivers, and consequences |
| [Diataxis](https://diataxis.fr/) | Separate explanation, how-to, reference, and tutorial needs |
| [ASD-STE100 Issue 9](https://www.asd-europe.org/news-media/news-events/news/simplified-technical-english-asd-ste100-issue-9/) | Consistent, controlled technical language |
| [GitHub diagrams](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-diagrams) | Mermaid in Markdown and host renderer version inspection |
| [Structurizr](https://structurizr.com/) and [LikeC4](https://likec4.dev/) | Multiple structural views from a maintained model |
| [Vale](https://docs.vale.sh/) | Configurable prose linting, not semantic or STE certification |

These sources inform the method. Archlens's limits and thresholds are local choices.

## Explain execution and data

Trace from trigger to outcome, including validation, branches, state changes,
external calls, transactions, async boundaries, failures, and recovery.
Use a sequence for order, a decision table for branch combinations, and a state view for lifecycle.

For data, document ownership, validation, transformations, authoritative stores,
consumers, consistency, access, retention, deletion, replay, and schema evolution.
An ER diagram alone does not explain where data moves.

## Explain design choices

Runtime rules and human design decisions are different.
Record human choices in ADRs with options, evidence, consequences, and review triggers.
Keep proposed, accepted, and superseded states separate from inferred evidence.
Never reconstruct a historical approval from source alone.

## Maintain with code

Review document impact in the same change as code, contracts, configuration, or infrastructure.
Update affected pages, not the whole handbook.
Use coverage patterns as prompts to review, then trace indirect consumers.
Add periodic audits based on change rate and risk.

## Use an honest language target

Archlens uses an ASD-STE100-inspired profile, not the copyrighted standard's dictionary.
It does not claim official "80% compliance".
The local target is a declared sentence-level editorial pass rate.
See the [writing rubric](../plugins/archlens/references/writing.md).

Correctness, evidence, and clear access rules remain mandatory regardless of that score.

## Measure comprehension

Ask a new reader to locate an entrypoint, trace a state change, identify a data owner,
explain a branch, explain a tradeoff, and find recovery behavior.
Measure a baseline before choosing time targets.
Do not optimize a writing score while readers still cannot answer those questions.
