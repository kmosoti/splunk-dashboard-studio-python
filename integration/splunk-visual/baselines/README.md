# Screenshot baselines

These reviewed target-specific Playwright baselines were generated from the exact official image
digests in `../images.json` with the full suite on July 22, 2026.

| Target | Suite | Screenshots |
|---|---|---:|
| 9.4.3 | full | 67 |
| 10.0.0 | full | 67 |
| 10.2.0 | full | 67 |
| 10.4.0 | full | 73 |

`manifest.json` records the image, architecture, browser harness version, expected counts, and a
SHA-256 digest over each target's sorted filename-and-file-hash inventory.
Ordinary CI uses `updateSnapshots: none` and fails if a required baseline is missing, extra, or
different. A manual candidate-baseline run uploads proposed files for human review; it never
commits them.
