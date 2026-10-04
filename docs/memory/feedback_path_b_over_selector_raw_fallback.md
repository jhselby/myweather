---
name: path-b-over-selector-raw-fallback
description: "Design rule (08-25): a cascade layer that can't beat its own raw gets killed, not routed around. Reject adding raw as a selector fallback — silent nets let cascades rot."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4c41e557-bb4a-4757-a036-04904a33e6db
  modified: 2026-08-25T16:52:34.052Z
---

# Path B over Path A — kill broken cascades, don't route around them

**Rule.** Any NBM (or HRRR) cascade layer that can't beat its own raw over a sustained window gets killed via `ENABLED = False` or dropped from its `*_FIELDS` whitelist. The L1 selector should NOT be extended to include raw sources as candidates alongside pipeline outputs.

**Why:** Joe explicitly considered a 4-way selector (HRRR raw / HRRR pipe / NBM raw / NBM pipe) as a way to protect users from broken cascades. Rejected on 2026-08-25. The reasoning:

- **Silent safety nets let cascade rot happen unnoticed.** If a broken cascade produces bad Prod but the selector routes users to raw, users are protected but there's no forcing function to fix the cascade. Meanwhile the NBM cascade rotted for a week before today's ships (v0.6.471 killed l5_nbm at +238% ΔMAE; v0.6.472 dropped sr/t/ws from l3_nbm at −22% to −5% pooled lift).
- **The walkforward + sentry loop already catches broken layers within days.** That's the loud, explicit forcing function. Extending the selector would trade that loudness for user comfort.
- **Cascades exist to beat raw.** A cascade that can't beat raw has no reason to exist. The right response is to kill or fix the layer, not shim around it. Path B is the *point* of building corrections in the first place.
- **The walkforward's "≥+2% earn-membership gate against raw" is the codified enforcement mechanism** for this rule.

**How to apply:**
- When designing new cascade layers or safety mechanisms, keep the selector 2-way (HRRR pipeline vs NBM pipeline). Do NOT add raw fallbacks.
- When a cascade layer flags as harmful (walkforward proposes DROP, or sentry HOT), the response is `ENABLED = False` or `*_FIELDS` trim — not a routing change to hide the harm.
- The scoreboard's `HRRR/NBM Pipeline Skill` columns (negative when cascade is worse than raw) are the visible signal. Diagnose there; act by killing.
- **One exception worth naming:** if a cascade layer goes bad for a field we *can't* fix quickly (e.g., needs weeks of new data) AND the user hit is severe, a short-lived raw fallback with an explicit expiration date is acceptable as an emergency measure. But default = kill, not shim.
