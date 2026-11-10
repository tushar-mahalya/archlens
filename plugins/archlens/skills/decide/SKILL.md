---
name: decide
description: "Draft an architecture decision record with evidence, alternatives, quality drivers, tradeoffs, and a review trigger."
argument-hint: "<decision, constraints, and supporting evidence>"
disable-model-invocation: true
context: fork
agent: general-purpose
background: false
metadata:
  internal: true
---

# Record a design decision

Decision context: $ARGUMENTS

Read `${CLAUDE_PLUGIN_ROOT}/references/contract.md`.
Read only "Decision record" in `${CLAUDE_PLUGIN_ROOT}/references/templates.md`.
With Python, run the bundled script's `config --root <project> --summary`.
Otherwise read the configuration reference. Read its map section when adding the record.
Do not assume access to the parent conversation.

Require an existing handbook or project `.archlens.json`. Otherwise suggest `/archlens:setup`.
If the problem, options, or decision authority is missing, ask for that information.
Do not invent a meeting, date, approving person, benchmark, or rejected option.

Draft a new record in the project's existing decision folder and numbering, such as an
adopted `docs/adr/`, not in a second handbook folder. Choose an unused ID.
Include context, quality drivers, feasible options, consequences, reversal cost, and review triggers.
Default to `proposed`. Use `accepted` only with supplied authorized approval evidence.
For a reconstruction, label the evidence basis inferred and leave historical rationale unknown.
Do not rewrite historical accepted decisions. Link superseding records in both directions.
Update the decision index and document map. Check links and return the concise handoff.
