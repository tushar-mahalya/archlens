# Launch film: work-in-progress handoff

Branch: `wip/launch-video`. This branch holds the editable source of the 24-second Archlens launch film.
It is **not approved**. The user asked for more rework. Do not merge it into `main` and do not render
a final MP4 until the user approves the preview.

## Quick start for the next session

1. Read this file, then [brag-plan.md](brag-plan.md) (story, look, timing) and
   [composition-brief.md](composition-brief.md) (rules and boundaries).
2. Read [composition/AGENTS.md](composition/AGENTS.md) (HyperFrames tooling guidance;
   `CLAUDE.md` is an identical copy).
3. Start the preview (see [Commands](#commands)) and review it with the user before you edit.
4. Keep [CREDITS.txt](CREDITS.txt) and [share-copy.txt](share-copy.txt) accurate after every change.

## Status

| Item | State |
| --- | --- |
| Composition | 1920 x 1080, 30 fps, 24.00 s, 720 frames, five scenes |
| Last automated check | 58/58 contrast checks, 15 layout samples, 300 motion samples, 0 errors, 0 warnings |
| Audio | All cues verified in full playback |
| Final render (`brag.mp4`) | **Not produced.** Waits for user approval |
| Poster (`brag.jpg`, baked into frame 0) | **Not produced.** See [Gotchas](#gotchas) |
| Published anywhere | No |

## User feedback so far

| # | Feedback | What was done |
| --- | --- | --- |
| 1 | Make an impressive launch film with the Brag skill. | Built a local 24 s, 16:9 HyperFrames composition from the pinned Brag workflow. |
| 2 | Better animation, more dramatic motion. | Added execution signals along the paths, coordinated transitions, a paper wipe into the decision, and an iris into the end card. |
| 3 | The opening scene (0-3.55 s) looks cluttered and unprofessional: inconsistent graphics, non-fluid motion. | Replaced the tangled graphics with three clean source anchors that converge on a question lens. The lens matches position, size, and velocity across the cut into the reveal. |
| 4 | Mention the portable Agent Skill. | The end card separates the Claude Code plugin command (`/archlens:setup`) from the portable Agent Skill (skills CLI). |
| 5 | Review before rendering; keep shared tools. | No render was made. Shared toolchain left intact. |
| 6 | **Still needs rework** (latest). | Open. Specific points were not yet given; start by asking the user what to change. |

## Scenes and next candidates

| Scene | File | Time | Current state | Review next |
| --- | --- | --- | --- | --- |
| Question | [question.html](composition/compositions/question.html) | 0.00-3.55 | Clean anchor diagram, matched lens | Settled hold may feel too static |
| Reveal | [reveal.html](composition/compositions/reveal.html) | 3.55-7.35 | Lens resolves into Archlens and the real command | The fast command-to-document cut |
| Execution | [execution.html](composition/compositions/execution.html) | 7.35-13.64 | Correct repeat-request branches (same data: same order ID; different data: `RequestConflict`, rollback) | Small-screen legibility; hold on the conflict branch |
| Decision | [decision.html](composition/compositions/decision.html) | 13.64-18.55 | ADR-001 stays **proposed** | Brightness of the paper wipe; iris pacing |
| Payoff | [payoff.html](composition/compositions/payoff.html) | 18.55-24.00 | Plugin command, repository, portable skill, MIT, music credit | Small-screen text size |

Scene start times and durations are set in [index.html](composition/index.html). Motion tokens are in
[index.motion.json](composition/index.motion.json). Shared styles are in
[film.css](composition/assets/film.css).

## Non-negotiable content rules

- Do not fabricate an agent session, dashboard, metric, benchmark, token saving, approval, or certification.
- Keep the exact product strings: `Archlens`, `/archlens:setup`, `RequestConflict`, `ADR-001`, `proposed`.
- The diagram may simplify the order-service example but must not change its validation, repeated-key
  behavior, transaction result, or decision status. Source pages are under
  [examples/order-service](../examples/order-service).
- Do not claim official ASD-STE100 compliance or universal agent support.
- Keep the music credit on the final card and in the share copy (CC BY 4.0).
- Banned looks: purple SaaS gradients, random particles, busy HUD ornament, fake app screens, strobing.

## Commands

The `package.json` scripts work on any machine with Node 22+ (they download HyperFrames 0.9.19):

```text
cd brag-output/composition
npm run dev      # preview in the browser
npm run check    # contrast, layout, and motion checks
npm run render   # ONLY after user approval; writes ../brag.mp4
```

Set `DO_NOT_TRACK=1` and `HYPERFRAMES_NO_TELEMETRY=1` before running them.

### Original Windows machine (pinned local toolchain)

The local toolchain lives in the ignored folder `.validation\brag-tools` and is not in Git:
HyperFrames 0.9.19, GSAP 3.15.0, Node 24.22.2, Chrome headless shell 152.0.7977.30, FFmpeg/FFprobe 9.0.2.
Keep that folder intact. The preview was last served at `http://127.0.0.1:3036/#project/composition`.

Start the preview in a separate shell:

```powershell
& 'C:\Users\tushsha2\source\archlens\.validation\brag-tools\hf.ps1' -Arguments @('preview','--foreground','--no-open','--port','3036','--json')
```

Lint, check, and frame snapshots:

```powershell
$T='C:\Users\tushsha2\source\archlens\.validation\brag-tools'; $P='C:\Users\tushsha2\source\archlens\brag-output\composition'; Set-Location $P
$node="$T\node-v24.22.2-win-x64\node.exe"; $hf="$T\node_modules\hyperframes\bin\hyperframes.mjs"
$W="$P\.hyperframes\opening-refinement-work"; New-Item -ItemType Directory -Force $W | Out-Null
$env:TEMP=$W; $env:TMP=$W; $env:HYPERFRAMES_CACHE_DIR=$W; $env:CI='true'; $env:DO_NOT_TRACK='1'; $env:HYPERFRAMES_NO_TELEMETRY='1'
$env:HYPERFRAMES_BROWSER_PATH="$T\cache\chrome\chrome-headless-shell\win64-152.0.7977.30\chrome-headless-shell-win64\chrome-headless-shell.exe"
$env:HYPERFRAMES_FFMPEG_PATH="$T\ffmpeg\ffmpeg.exe"; $env:HYPERFRAMES_FFPROBE_PATH="$T\ffmpeg\ffprobe.exe"; $env:PATH="$T\node-v24.22.2-win-x64;$T\ffmpeg;$env:PATH"
& $node $hf lint --json
& $node $hf check --samples 15 --json --snapshots
& $node $hf snapshot --at '0,0.75,2,3.4,3.55,3.7,4.35,21.5' --no-end --output "$P\.hyperframes\artifacts\snapshots\review-<new-name>" --json
```

## Gotchas

- `hyperframes.json` and `hyperframes.lock.json` reference `compositions/components/code-terminal-run.html`,
  which does not exist. The film uses its own command strip. Remove both references or restore the
  component on purpose; checks currently pass with the dangling reference.
- The brief requires the best settled frame as a poster baked into frame 0. Frame 0 is currently the
  opening question. Decide the poster before the final render.
- Keep `assets/audio/select-waveform.wav`. Its silence padding lets the Studio draw the waveform;
  `data-media-start="0.03501133786848073"` in `index.html` keeps the original click timing.
- Keep browser profiles and scratch folders outside the watched `composition` folder, or the preview reloads.
- `snapshot --output` clears its destination. Use a new folder name each time.
- Old snapshot set `motion-review-final` predates the opening redesign; `opening-review-final` is current.
  Both are local caches and are not in Git.

## What is in Git and what is not

| In this branch (sources) | Not committed (regenerable or local) |
| --- | --- |
| Scene HTML, `index.html`, `index.motion.json`, `film.css` | `composition/.hyperframes/` (editor history with machine paths, snapshots, preview state) |
| Bundled fonts, audio, GSAP, and their licenses | `composition/.thumbnails/`, `composition/.waveform-cache/` |
| `hyperframes.json`, lock file, `meta.json`, `package.json` | Rendered `*.mp4` and `*.jpg` (attach to a release instead) |
| Plan, brief, credits, share copy, this handoff | `.validation/` toolchain at the repository root |

Pre-commit excludes `brag-output/composition/assets/` so vendored and binary files stay byte-for-byte.

## Finishing checklist

- [ ] Collect the user's specific rework points and apply them scene by scene.
- [ ] `npm run check` (or the local commands) shows 0 errors and 0 warnings; inspect a settled frame per scene.
- [ ] Resolve the dangling component reference and the poster decision.
- [ ] Get explicit user approval of the preview.
- [ ] Render; verify 1920 x 1080, 30 fps, 720 frames, 24.00 s, H.264/AAC, audio present.
- [ ] Publish the MP4 as a release asset or README media only if the user asks. Open a PR; do not push to `main`.

## Project context (outside the film)

- Archlens v0.2.0 is released. `main` is protected by rulesets: changes need a pull request,
  a code owner review, and the `CI passed` check. See [CONTRIBUTING.md](../CONTRIBUTING.md).
- skills.sh listing is pending. Direct install works. Listing is driven by genuine telemetry-enabled
  installs; do not create artificial installs.
- Do **not** add `Co-authored-by` trailers to commits in this repository (explicit maintainer request).
