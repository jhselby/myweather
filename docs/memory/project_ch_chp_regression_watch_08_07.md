---
name: ch-chp-regression-watch-08-07
description: "ch two consecutive days of deterioration 2026-08-06 (+25% compressed from usual +65-78%) and 2026-08-07 (-27% flipped negative). Layer walk isolates chp as cause: L3 fine, prod_real terrible. Watching one more day before acting."
metadata: 
  node_type: memory
  type: project
  originSessionId: d5b3b340-bcb5-4198-bf9b-651541917300
  modified: 2026-08-07T22:55:02.550Z
---

# ch (cloud_cover_high) regression watch — chp suspect

## Status: WATCHING one more day (as of 2026-08-07 EOD)

- 2026-08-06: raw 20.95 → prod_real 15.73 (**+24.9% help**, but compressed from usual +65-78%)
- 2026-08-07: raw 8.53 → prod_real 10.86 (**−27.4% hurt**, bias +7.5 = over-forecasting)

Historical context: 07-31 through 08-05 was consistently +64 to +75% help. ch had been the best field on the scoreboard for weeks.

## Layer walk (08-07 24h, per band)

```
band    raw    L3    prod_real
0-5h   3.75   3.17    3.34   (+11% ok)
6-11h  6.48   5.58   11.12   (L3 helps +14% → prod hurts −72%)
12-23h 6.87   5.52   11.40   (L3 helps +20% → prod hurts −66%)
24-47h 10.08  7.00   12.26   (L3 helps +31% → prod hurts −22%)
```

L3 is doing its job. Everything past L3 (L4 + chp) is trashing it. Most likely **chp** (ch persistence gate, LIVE 07-19 v0.6.358) — same shape as sr Lsb Day 1 regression yesterday: correction over-committed on prior-window signal that the current regime (cloud clearing) doesn't support.

## Decision trigger for 2026-08-08 morning check

- If ch `prod_real` at 6-11h / 12-23h / 24-47h is still worse than raw → **emergency demote those cells per v0.6.382t playbook** (leave 0-5h alone, still positive). Live-layer change, reversible.
- If ch recovers (prod flips positive again, or raw and prod converge) → the two bad days were the weather clearing, not a chp break. No action.
- If it's mixed / thin data → hold, check next day.

## Related

- [[project_ch_persistence_gate_ship]] — chp ship history
- [[project_chp_midlead_regression_watch]] — prior mid-lead regression + v0.6.382t demote playbook
- [[project_sr_lsb_flip_gate]] — same failure shape (Lsb Day 1) but sr recovered Day 2
