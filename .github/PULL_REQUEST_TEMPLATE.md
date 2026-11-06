## Summary

<!-- What changes, and why? Link the issue or discussion, for example "Closes #12". -->

## Type

- [ ] Fix
- [ ] Feature
- [ ] Documentation
- [ ] Build, CI, or maintenance

## Checks

- [ ] The PR title follows [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, ...).
- [ ] `pre-commit run --all-files` passes.
- [ ] `python -m unittest discover -s tests` passes.
- [ ] If I changed native plugin resources, I ran `python tools/sync_portable.py` and committed the generated portable files.
- [ ] If I changed instructions, `python tools/prompt_budget.py` passes and the documented budgets are current.
- [ ] I updated user documentation and `CHANGELOG.md` where relevant.
- [ ] I did not include secrets, private source code, or customer data.

## Context cost

<!-- Does this add loaded instructions, hooks, automatic commands, or new dependencies? If yes, explain why. -->
