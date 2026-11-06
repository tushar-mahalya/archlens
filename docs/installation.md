# Install and manage Archlens

## Requirements

- A current Claude Code installation with plugin and forked-skill support.
- Git for marketplace installation from GitHub.
- An existing Claude Code account or API configuration.

Install validation is tested with Claude Code 2.1.318.
Use a current version if fields such as `background: false` are not supported.
Python and Node are not required for normal plugin use.

## Install for all your projects

Inside Claude Code:

```text
/plugin marketplace add tushar-mahalya/archlens
/plugin install archlens@archlens
```

Choose user scope. The marketplace name and plugin name are both `archlens`.
Your teammates do not receive a user-scope installation automatically.
For a team repository, choose project scope and review the resulting settings change.

From a terminal, the equivalent is:

```text
claude plugin marketplace add tushar-mahalya/archlens
claude plugin install archlens@archlens --scope user
```

## Use a downloaded release

Download and extract the release ZIP.
The extracted `archlens-<version>` folder must contain `.claude-plugin` and `plugins`.
Keep that folder: local marketplaces can read directly from it.

From PowerShell:

```powershell
claude plugin marketplace add "C:\Tools\archlens-0.1.1"
claude plugin install archlens@archlens --scope user
```

From macOS or Linux, pass the extracted POSIX folder path instead.
Do not register the raw marketplace JSON URL; its relative plugin source needs the whole repository.

## Try without installing

From a repository clone:

```text
claude --plugin-dir ./plugins/archlens
```

Use `.\plugins\archlens` in Windows commands when appropriate.
This loads the plugin for that session only.

## First use

1. Open a small project in Claude Code.
2. Run `/archlens:setup`.
3. Review the generated handbook and its evidence.
4. Run `/archlens:explain` with a specific journey.
5. After a code change, run `/archlens:update` with your local base ref.
6. Run `/archlens:check`.

The supplied [order example](../examples/order-service/README.md) is a safe place to start.
Setup is a writing task. Check and explain are read-only by instruction.
Keep normal tool approvals enabled.

## Update

From a terminal:

```text
claude plugin marketplace update archlens
claude plugin update archlens@archlens --scope user
```

Restart or reload if Claude Code asks.
Do not edit files in the installed plugin cache. Put preferences in your user or project config.
Plugin updates do not overwrite your project's handbook.

## Remove

```text
claude plugin uninstall archlens@archlens --scope user
claude plugin marketplace remove archlens
```

Removal does not delete your project documents or Archlens preference files.
Review and remove those separately only if you no longer need them.

## Troubleshooting

| Symptom | Action |
|---|---|
| `/archlens:setup` is missing | Check `/plugin`, scope, and enabled status; reload or restart |
| It does not start automatically | Expected: all commands are manual to limit idle context |
| It forgot a previous discussion | Supply the relevant decision or scenario in the command |
| Python is missing | Skills still work; install Python only if you want deterministic local checks |
| Git base ref fails | Supply a local ref that exists; the tool never fetches |
| `map.json` is missing | Run setup or map your existing pages using the configuration reference |
| Config is rejected | Fix the named field; unknown keys and malformed JSON are errors |
| Organization blocks the plugin | Ask your administrator; do not bypass the policy |
| Large report omits records | Save full `--json` output locally and inspect the relevant records |

An agent can still make errors. Verify generated explanations and review proposed decisions.
