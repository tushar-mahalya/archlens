# Install and manage Archlens

## Choose a distribution

| Distribution | Best for | Installation requirements |
|---|---|---|
| Native Claude plugin | Claude Code with explicit, isolated commands | Current Claude Code, Git, and an account or API configuration |
| Portable Agent Skill | Other compatible coding agents, or a portable Claude skill | A skills-compatible agent, Git, Node.js 22.20+, and npm/npx |

Python 3.9+ enables the plugin hooks, freshness tracking, and deterministic checks.
The model-assisted workflows still run without it. The hooks call `python3`, so on
Windows make sure a `python3` command exists. Normal agent and provider charges still apply.
Choose one distribution per Claude Code installation to avoid duplicate discovery.
Native plugin validation and hooks are tested with Claude Code 2.1.319.

## Native Claude plugin

### Install for all your projects

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

### Use a downloaded release

Download and extract the release ZIP.
The extracted `archlens-<version>` folder must contain `.claude-plugin` and `plugins`.
Keep that folder: local marketplaces can read directly from it.

From PowerShell:

```powershell
claude plugin marketplace add "C:\Tools\archlens-0.4.0"
claude plugin install archlens@archlens --scope user
```

From macOS or Linux, pass the extracted POSIX folder path instead.
Do not register the raw marketplace JSON URL; its relative plugin source needs the whole repository.

### Try without installing

From a repository clone:

```text
claude --plugin-dir ./plugins/archlens
```

Use `.\plugins\archlens` in Windows commands when appropriate.
This loads the plugin for that session only.

### First use

1. Open a small project in Claude Code.
2. Run `/archlens:setup`. If the project already has architecture docs, setup adopts
   them in place and fixes what the code contradicts. Use `/archlens:setup new` for a separate handbook.
3. Review the generated pages, the edits to existing docs (`git diff`), and their evidence.
4. Run `/archlens:explain` with a specific journey.
5. Ask Claude to change some covered code. The stop hook reports the stale pages.
6. Ask Claude to commit. Archlens holds the commit once, the update runs in an isolated task,
   and the docs land in the same commit. You can also run `/archlens:update` at any time.
7. Run `/archlens:check`, then try `/archlens:learn tour`.

The supplied [order example](../examples/order-service/README.md) is a safe place to start.
Setup is a writing task. Check, explain, and learn are read-only by instruction.
Keep normal tool approvals enabled.

### Update

From a terminal:

```text
claude plugin marketplace update archlens
claude plugin update archlens@archlens --scope user
```

Restart or reload if Claude Code asks.
Do not edit files in the installed plugin cache. Put preferences in your user or project config.
Plugin updates do not overwrite your project's handbook.

### Remove

```text
claude plugin uninstall archlens@archlens --scope user
claude plugin marketplace remove archlens
```

Removal does not delete your project documents or Archlens preference files.
Review and remove those separately only if you no longer need them.

## Portable skill with skills.sh

In the project directory, install for the agent you use. This example uses Codex:

```text
npx skills@1.7.6 add tushar-mahalya/archlens --skill archlens --agent codex --copy --yes
```

Replace `codex` with a selector from the table below. Omit `--agent`, `--copy`,
and `--yes` for the installer's interactive choices. `--copy` creates independent
files instead of links; without it, the installer may use links and platform
fallbacks. A project install creates skill and lock files in the current project.
Review them before committing them. To install for your user account instead,
add `--global`:

```text
npx skills@1.7.6 add tushar-mahalya/archlens --skill archlens --agent codex --copy --global --yes
```

The CLI version above is pinned to the version exercised by Archlens CI.
The installed skill is fetched from the repository's current default branch.
Restart the agent or reload its skills, then ask:

```text
Use the Archlens skill to explain how an order flows through this project.
```

Other operations are setup, update, check, decide, and learn. Specify the scenario,
local base ref, or decision evidence in your request. Some hosts also offer an
explicit skill selector or slash command. Unlike the native Claude plugin, the
portable skill is not guaranteed to run in a fork or to remain manual-only.

### Adapter coverage

The pinned skills CLI is exercised in isolated project and global installations
for the selectors below. The complete installed bundle and checker are tested.
These are installer tests, not end-to-end runs of each agent or model.
Discovery, permissions, activation, isolation, and model output depend on the
agent version and its settings.

| Agent | Selector | Discovery notes |
|---|---|---|
| Claude Code | `claude-code` | Portable skill; native plugin remains the recommended Claude option |
| Codex | `codex` | Uses the shared `.agents/skills` location |
| Cursor | `cursor` | Verify discovery in the current Cursor version |
| GitHub Copilot | `github-copilot` | Supported locations vary by Copilot surface |
| Gemini CLI | `gemini-cli` | Uses the shared `.agents/skills` alias |
| OpenCode | `opencode` | Supports shared `.agents/skills` locations |
| Roo Code | `roo` | Uses its `.roo/skills` location |
| Devin for Terminal | `devin` | Use for current Devin environments |
| Cline | `cline` | See the discovery caveat below |
| Windsurf | `windsurf` | See the discovery caveat below |

Other selectors offered by the CLI are not tested by this project.
Consult the [skills CLI agent list](https://github.com/vercel-labs/skills/blob/main/docs/agents.md)
and your host's skill documentation before using them.

**Cline:** the tested CLI places Cline's copy in `.agents/skills`, but
[Cline's documentation](https://docs.cline.bot/customization/skills) lists
`.cline/skills` for project and user skills instead. If Cline does not discover
Archlens, copy the **whole** installed `archlens` directory into the documented
`.cline/skills` location and reload Cline. A manually copied directory is not
managed by `skills update` or `skills remove`; review and replace or remove it
yourself when needed.

**Windsurf and Devin:** the tested `windsurf` adapter installs to
`.windsurf/skills` for projects and `~/.codeium/windsurf/skills` globally.
Current [Devin Local documentation](https://docs.devin.ai/desktop/devin-local/customizations)
also reads the legacy project path, but lists different global paths.
For current Devin Local or Devin CLI, use the `devin` selector instead.
Verify discovery in your particular Windsurf version.

### Update or remove a portable skill

From the project directory, use `npx skills@1.7.6 check` and
`npx skills@1.7.6 update` to inspect and update installed skills.
For user-level skills, use `npx skills@1.7.6 update --global`.
These commands can update other skills in the selected scope too.

Remove Archlens from the project with:

```text
npx skills@1.7.6 remove archlens --yes
```

Add `--global` to remove the user-level copy instead. A shared `.agents` copy
may serve several agents, so removing it can affect all of them.
Neither removal nor updating deletes your architecture handbook or preferences.

### Installer privacy and skills.sh listing

The `skills` CLI and npm download software and repository files over the network.
The CLI has its own telemetry and may contact security-assessment services;
these are separate from Archlens. To opt out of CLI telemetry, set
`DISABLE_TELEMETRY=1` or `DO_NOT_TRACK=1` in the shell before running it.
In PowerShell, for example, use `$env:DISABLE_TELEMETRY = "1"`.
The pinned CLI also skips its security-assessment request when telemetry is
disabled; opt-out does not make npm or Git downloads offline.

According to the [skills.sh FAQ](https://skills.sh/docs/faq), public skills are
listed automatically after telemetry-enabled installs; no manual registration
step is documented. An opt-out install does not contribute to the leaderboard.
Listing is not required for a direct GitHub installation to work.

## Troubleshooting

| Symptom | Action |
|---|---|
| `/archlens:setup` is missing | Check `/plugin`, scope, and enabled status; reload or restart |
| Portable skill is missing | Check the selected agent and scope, restart or reload it, and verify its supported skill path |
| Native plugin does not start automatically | Expected: Claude plugin commands are manual to limit idle context |
| It forgot a previous discussion | Supply the relevant decision or scenario in the command |
| Python is missing | Skills still work; install Python only if you want deterministic local checks |
| Git base ref fails | Supply a local ref that exists; the tool never fetches |
| `map.json` is missing | Run setup or map your existing pages using the configuration reference |
| Config is rejected | Fix the named field; unknown keys and malformed JSON are errors |
| Organization blocks the plugin | Ask your administrator; do not bypass the policy |
| Large report omits records | Save full `--json` output locally and inspect the relevant records |

An agent can still make errors. Verify generated explanations and review proposed decisions.
