---
name: scoreboard-vocab-winning-losing-flat
description: "On the debug page scoreboard tiles and per-field scoring surfaces, always use \"winning / flat / losing\" for the three lift buckets. Do not introduce \"beat\", \"improved\", \"regress\", \"positive/negative\", \"green/amber/red\" as replacement words."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c4abe134-966d-4faf-978d-a5fc16044c53
  modified: 2026-08-19T23:20:09.680Z
---

Use **"winning / flat / losing"** as the single vocabulary for the three lift buckets on every debug-page scoreboard surface (headline strip cells, per-field lift columns, aggregate rollups, National Source Score).

**Why:** Joe has called out vocabulary drift repeatedly across the 08-19 afternoon session. In one session Claude introduced "beat / flat / regress", then "improved / flat / regress", then briefly "STRONG/GOOD/WATCH/REGRESS" (Verdicts row, since ripped). This drift is the exact "consistency by default" and "session-drift" failure — a new tile inheriting slightly different words breaks the reader's mental model. See [[feedback_consistency_by_default]] and [[feedback_ui_incremental_drift]].

**How to apply:** Before adding or renaming any bucketed lift label on the debug page, check what other tiles in the same section already say. If a new word feels more natural for one tile in isolation, that's not a reason to introduce it — the loss of cross-tile consistency outweighs the gain. If Joe's mock uses a different word, either match the mock or ask; do not silently pick a third option.

The three buckets refer to the same thresholds used across all scoring surfaces (green ≥ +5%, red ≤ −1%, else flat). "Winning" also matches the "NBM wins / HRRR wins" language in the National Source Score tile.

Related: [[feedback_ui_incremental_drift]], [[08-19-afternoon-handoff]].
