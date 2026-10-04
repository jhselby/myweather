---
name: tau-streak-gate-limits
description: "The decay_tau_tuning streak gates set membership (field in ≥5% winning set), NOT the specific τ value. A field can stay in the winning set for many consecutive reads while its best-τ wanders — the streak alone doesn't distinguish \"stable per-field τ\" from \"stable ≥5% membership with a wandering τ.\""
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 36fb9e26-1fb0-4ebe-8ddf-99f1fed2e7ba
---

decay_tau_tuning's CONFIRMATION_STREAK counts consecutive daily reads where the winning set (fields with ≥5% held-out gain vs τ=14) is unchanged. It does NOT track which τ value each field's win came at.

**Why:** The 5% floor is noise-adjacent (ws τ=7 shipped v0.6.271 and reverted v0.6.279 for exactly this). The streak was added to gate the "IMPLEMENT" verdict against noise flips in-and-out of the winning set. But once a field IS reliably in the winning set, the specific best-τ can still swing across reads and the streak keeps ticking.

**How to apply:** When acting on an IMPLEMENT verdict, check the history of best-τ values for the winning field, not just the streak count. Documented case: pa swung 28 (2026-06-22) → 42 (2026-07-13) → 7 (2026-07-18) across three reads, all inside the winning set. Each ship was "confirmed" by streak but the τ shipped was different each time. Re-validate weekly and expect swings; the streak gate protects against set churn, not τ instability. Ties to [[project_07_18_session]].

**Watch trigger — pa τ retirement candidate (added 2026-07-18 PM):** The 15:08 Fitter run after shipping pa τ=42→7 showed the fitted corrections BARELY MOVED (lead 12: -0.037 τ=42 → -0.035 τ=7; lead 24: -0.034 → -0.036). If the tuning script's +5.9% held-out win isn't visible in the fitted output, the win is likely fitting noise on a sparse rare-event signal (pa correction magnitude is only ~0.035 in/hr; small shifts in the recency-weighted mean of a mostly-zero distribution are exactly where held-out MAE gets fooled). **Trigger:** if next week's re-validation shows another τ swing (7 → something else) AND the fitted corrections still barely move between reads, retire per-field τ for pa entirely and revert to global τ=14. Same reasoning as the 07-02 ws τ=7 revert.
