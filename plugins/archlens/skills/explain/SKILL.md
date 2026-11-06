---
name: explain
description: "Trace a named execution or data flow through source and documentation, with a small diagram and evidence. Does not edit files."
argument-hint: "<scenario or question>"
disable-model-invocation: true
context: fork
agent: general-purpose
background: false
metadata:
  internal: true
---

# Explain a scenario

Question: $ARGUMENTS

Read `${CLAUDE_PLUGIN_ROOT}/references/contract.md`.
If no question was supplied, request a scenario and stop.
Do not edit files or require an existing handbook.
Start from the scenario's entrypoint or an existing index. Load configuration only
if needed to locate a custom handbook. Do not load templates or the style manual.

Trace from the actual entrypoint to the outcome. Include identity and validation,
branch conditions, state changes, external calls, and relevant failure or recovery behavior.
Follow async consumers when needed. Distinguish configured behavior from observed production behavior.
Use targeted source reads rather than loading the entire repository.

Return a short explanation, a Mermaid diagram, and a step table with source references.
Link design rationale only when a record supports it. Label inference and unknowns.
State the scope and any untraced paths. Follow the contract's output budget.
