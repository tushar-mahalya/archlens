# Hyperframes composition brief: Archlens

## Objective

Create a 24-second cinematic launch film that makes architecture comprehension
feel tangible. Follow [the storyboard](brag-plan.md), not a generic launch template.

## Deliverables

- `composition/`: editable local Hyperframes project.
- `brag.mp4`: 1920 x 1080, 30 fps, 24 seconds, H.264/AAC.
- `brag.jpg`: the strongest settled product frame, also baked into video frame zero.
- `share-copy.txt`: one canonical, ready-to-post caption with music attribution.
- `CREDITS.txt`: asset provenance, licenses, and source-content notes.

## Source material

- [Product claims and commands](../README.md).
- [Fictional example](../examples/order-service/README.md).
- [Execution evidence](../examples/order-service/order_service.py).
- [Actual runtime page](../examples/order-service/docs/architecture/runtime/submit-order.md).
- [Actual decision proposal](../examples/order-service/docs/architecture/decisions/ADR-001.md).
- [Data ownership](../examples/order-service/docs/architecture/data.md).

Required exact product strings: `Archlens`, `/archlens:setup`, `RequestConflict`,
`ADR-001`, `proposed`. The diagram can simplify the sample page, but cannot change
its input validation, repeated-key behavior, transaction result, or decision status.

## Look and motion

LOOK: `#101918` instrument ground, `#F5F5E9` ink, `#C9FF65` signal,
`#70DDD0` secondary, `#EEEFE3` paper; Sora 600/700 and IBM Plex Mono 400/500;
192 px title-safe inset, 2 px rules, 24 px corners.

BANNED: neon purple gradients, fake application screens, random particles,
busy HUD ornament, unreadable claims, certification badges, and invented metrics.

Use one editable sub-composition per scene. Keep real text in HTML. Build each
scene with one paused, registered GSAP timeline and explicit from/to states.
Use fast entrances, long-tailed landings, and readable holds. Make paths draw in
execution order. Transition to paper for the decision rather than adding another
identical dark feature card. Palette, product name, tagline, and URL are variables.

## Sound

Copy the chosen Brag music and only the selected low-risk Kenney effects into
local assets. Trim/fade locally, preserving attribution. The outro begins at
18.55 s, with CTA motion near the track's supplied 20.19 s cue. Music supports
the narrative; it does not dictate all text timing. Voiceover remains disabled.

## Boundaries and verification

Keep all rendering local and disable tool telemetry. Do not publish, authenticate,
upload project content, or use paid generation. Avoid relying on CDN assets during
render. Do not claim a browser check passed until text was actually audited.
Inspect a settled frame from every scene, verify audio and exact output shape,
and choose the poster for its composition rather than an arbitrary timestamp.
