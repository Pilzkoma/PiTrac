# Calibration capture set — 2026-08-08 (springs removed, plate bolted)

24 pairs, the source of both intrinsics and extrinsics from 2026-08-09 until the
2026-11 recapture. Archived here on 2026-11-07 because the cameras were
re-aimed on their screws while moving into a reprinted enclosure, which changes
their relative pose.

The full record of this set — capture conditions, coverage, what came out and
the subset checks — is in `../README.md`, section "The current set — 2026-08-08".
To re-run its solve:

```
SET=../../sp1_vision/calibration_images/2026-08-08_bolted
```

and pass `--square-mm 24.27` (the 24.0 used in the original solve was 1.1 % short).
