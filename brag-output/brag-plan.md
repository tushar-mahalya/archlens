# Archlens: See the system

## Inspection rubric

1. **Product:** Archlens offers a Claude Code plugin and a portable Agent Skill distributed with the skills CLI. The film demonstrates the Claude Code workflow.
2. **Strongest claim:** "Understand how a project works, how its data moves, and why its design exists."
3. **Visual hook:** Three source anchors converge on one clear question; the question becomes the lens that illuminates the execution path.
4. **Real product material:** The order-service runtime page, its request-key decision proposal, and the actual `/archlens:explain` and `/archlens:setup` commands.
5. **Shortest satisfying film:** 24 seconds, with enough time to read the two repeat-request outcomes.
6. **Tone:** Cinematic, with the precision of a technical instrument rather than a generic AI advertisement.
7. **Audio:** A restrained rhythmic music bed, warm transitions, and two soft route-selection accents. No narration.
8. **Caption:** "The code runs. Now understand it. Archlens turns source evidence into execution maps, data flows, and explicit tradeoffs."
9. **User flow:** Invoke a scenario command, follow the documented execution paths, then inspect the decision and its consequences.

## Creative premise

The lens is a way of seeing, not a fictional application interface. The film moves
from ambiguity to a precise execution trace, then opens the design decision behind
it. The showcased handbook is real repository content, styled for the film.
There is no fabricated agent recording, production dashboard, customer data,
benchmark, measured token saving, or claim of universal agent support.

## Visual identity

Archlens currently has no website, brand stylesheet, or existing logo asset.
This film introduces a visual direction without claiming it was extracted from one.

- LOOK: technical drawing meets a premium instrument display; ground `#101918`;
  ink `#F5F5E9`; signal `#C9FF65`; secondary `#70DDD0`; paper `#EEEFE3`;
  Sora 600/700 display, IBM Plex Mono 400/500 annotations; 192 px title-safe inset;
  2 px structural rules; 24 px panel corners; no decorative browser chrome.
- BANNED: purple SaaS gradients, fake analytics, gratuitous particles, unreadable
  terminal dumps, invented approvals, oversized feature-card grids, strobing.
- Hero: source paths and a precise diagram, not stock footage or an avatar.
- Type: 88-158 px headlines, 31-48 px outcomes, at least 28 px annotations.

## Format and duration

Landscape, 1920 x 1080, 30 fps, 24.00 seconds, 720 frames.

## Storyboard

| Scene | Time | Duration | Picture and essential copy |
|---|---|---|---|
| Question | 0.00-3.55 | 3.55 s | Three source anchors connect to a clean question lens. "The code runs. But why?" The question settles quickly and holds. |
| Reveal | 3.55-7.35 | 3.80 s | The lens resolves the drawing. Archlens. "See the system." Actual command: `/archlens:explain submit an order`. |
| Execution | 7.35-13.64 | 6.29 s | A styled excerpt of the real handbook. "Follow the execution." Same key + same data returns the same order ID. Different data raises `RequestConflict` and rolls back. |
| Decision | 13.64-18.55 | 4.91 s | A deliberate cut to paper. "Know the tradeoffs." ADR-001, explicitly proposed. Unique request keys prevent duplicate rows; callers must manage stable keys. |
| Payoff | 18.55-24.00 | 5.45 s | Return to the instrument display. "Stop guessing. See the system." Label `/archlens:setup` for the Claude Code plugin; show the repository URL, MIT/open-source marker, portable Agent Skill via the skills CLI, and music attribution. |

Durations sum to 24.00 s. The opening question is visible at frame zero; other
essential text lands early and then holds. A short label gets at least 0.8 s
settled; a sentence gets about 0.3 s per word. The runtime
diagram is an explicitly selected-path view of the fictional example, not a claim
that every exception is displayed.

## Motion direction

The opening uses a restrained constellation of source anchors rather than a
decorative tangle. Its question mark and circle match the reveal lens in position,
size, and velocity at the cut. The command strip opens into the runtime document;
a signal travels through the nodes and selects the two branches in order. The
decision arrives as a paper wipe; its proposed-status stamp becomes the iris into
the final card. These moves finish before the important reading holds, and the
ending keeps the real setup command, repository, and music credit.

## Audio direction

- Music: Brag's bundled "Happy Beats / Business Moves, Vol. 10" by Sascha Ende.
- Treatment: first 24 seconds, restrained gain, short fade-in and 1.5 s fade-out.
- Cue source: the track's bundled `.music-cues.md`, inspected before composition.
- Estimated beat spacing: 0.545 s; supplied cue estimates are guidance, not a
  claim of newly measured synchronization.
- Major locks: the final scene starts at 18.55 s; the repository CTA lands near
  20.19 s. Other timing follows reading time rather than every beat.
- SFX: low-risk Kenney soft impact and selection accents; no sharp repeating clicks.
- Audio-reactive treatment: none. Explicit route motion is the focal movement.
- No voiceover, generated speech, remote render, account sign-in, or paid media.
- Attribution accompanies the video, appears on the final card, and is included
  in the canonical share caption.

## Source and workflow

- Brag skill: `latent-spaces/brag` at `669ab9286aa28b6c3ee30e75f181ee74319d012a`.
- Archlens source: the published v0.1.1 examples and current plugin/skill distribution information supplied for this edit.
- Hyperframes: pinned local CLI; editable, seek-safe HTML scenes; local assets.
- Gate: nonzero text contrast coverage, zero check errors, visual frame inspection,
  matching output duration/frame count, audio verification, best-frame poster
  baked into frame zero.
