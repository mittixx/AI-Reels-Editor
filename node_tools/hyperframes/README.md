# HyperFrames master compositor

HyperFrames `0.8.12` is the only master timeline in AI Reels Editor v1.3.4.
Python creates a per-project composition from a validated `render_plan.json`, then runs
`lint → check → render`. Templates and components in this folder are reusable authoring assets;
AI never writes a new full HTML/CSS project for every Reel.

The wrapper invokes only the installed local CLI, sets `HYPERFRAMES_NO_UPDATE_CHECK=1`, and never
uses an implicit runtime package download.
