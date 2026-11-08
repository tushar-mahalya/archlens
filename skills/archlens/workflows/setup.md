# Set up Archlens

Task context: the relevant part of the user's request

Read `<skill-dir>/references/contract.md`. Read only the "Document map" and
"Freshness and agent context" sections of `<skill-dir>/references/configuration.md`.
With Python 3.9+, resolve preferences with the bundled `scripts/archlens.py config --root <project> --summary`.
Without Python, also read that reference's first section.
Read only the "Initial coverage" and "Trace execution and data" sections of
`<skill-dir>/references/workflow.md`.
Load the relevant section of `<skill-dir>/references/templates.md` only
when creating that page. Do not load the complete template catalog.

The user explicitly requests documentation setup. Work in the current project unless
the argument selects another folder. Resolve configuration before any edits.
Do not assume conversation history is available.

1. Inspect existing documentation, entrypoints, contracts, configuration, and tests.
2. Select a bounded scope. Start with context, main units, and one important journey.
3. Trace the journey, including branch conditions, data changes, and failure behavior.
4. Create or extend the handbook. Do not overwrite or move existing documents.
5. Add an index, coverage gaps, glossary terms, and a `map.json` document map.
   Existing documents can be mapped without rewriting them.
6. Draft decisions only when evidence supports a significant design choice.
   Mark missing historical rationale as unknown.
7. Check links and diagrams with available local tools.
8. With Python 3.9+, run the bundled `scripts/archlens.py sync --root <project> --all`
   to record the freshness baseline. Without it, state that freshness is not tracked.
9. This host may not load a handbook map at session start.
   Offer to set `"contextFile": "AGENTS.md"` in `.archlens.json`, then run
   `context --root <project> --write`. Ask before you edit any agent instruction file.
   Follow the contract's handoff.

Do not install packages, change application source, commit, or publish.
If the project contains multiple systems, ask which to document first.
If permissions or evidence block work, report the exact blocker rather than inventing details.
