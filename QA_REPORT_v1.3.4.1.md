# QA Report — AI Reels Editor v1.3.4.1

Hotfix date: 2026-08-24. OpenAI API was not used.

## FPS hotfix

- `VideoAnalyzer` preserves the chosen ffprobe rational frame rate instead of deriving the render
  rate from a float.
- `VideoInfo` and `RenderPlan` carry canonical `fps_rational`; HyperFrames receives that exact value.
- HyperFrames command no longer formats FPS as a decimal. Examples: `30/1`, `25/1`,
  `30000/1001`, `60000/1001`.
- The v1.3.4 QA report was archived; this is the only current QA report.

## Tests

- pytest: **151 passed, 1 skipped** (Windows-only `.cmd` subprocess test is skipped on Linux).
- New FPS regression tests: 30, 25, 29.97, 59.94; direct ffprobe rational propagation; HyperFrames
  command assertion proving `30.000000` is absent.
- Ruff: passed.
- mypy: passed (48 source files).
- Python compile/import and Motion Canvas TypeScript/Node syntax: passed.

## Limitations

No Windows/browser render was run in this Linux environment. The v1.3.4 Windows browser release
gate remains outstanding; this hotfix only addresses the confirmed FPS argument failure.
