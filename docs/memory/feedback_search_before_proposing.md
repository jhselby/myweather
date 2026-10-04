---
name: feedback-search-before-proposing
description: "Before proposing to build a new analysis metric, search the analysis/ directory first for existing implementations. Documented 2026-08-06 after proposing BSS-vs-climatology as a new script when `pp_brier_decomposition.py` line 121 had been emitting `brier_skill_vs_climatology` for months. Costs user's time; costs user's trust in your grasp of the codebase."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 57d4089d-4089-4ad5-a9a4-2ee10689764d
  modified: 2026-08-06T17:33:29.733Z
---

# Search the codebase before proposing a new metric

## Rule

Before proposing to build a new analysis script, dataset column, sentry, or metric, **grep the existing `analysis/` directory** for anything that already computes it. Not just by name — by concept.

**Why**: You'll otherwise propose to duplicate what already exists, wasting user's time reading a full scoping doc for work that's already done. The user's grasp of what's in the codebase is stronger than yours; when you propose something new that they know already exists, they lose trust in your working memory of the project.

**How to apply**: When about to propose a script, spend 30 seconds first with:
- `grep -rn "concept_keyword" analysis/`
- `ls analysis/ | grep <field or topic>`
- Skim similar-named scripts to see what they already emit.

Only THEN propose new work if truly missing.

## The 2026-08-06 incident

Session context: pp calibration workstream, all fixed-effect corrections HOLDing. User asked "what could we do about pp — both to judge it and to improve it?" I proposed:

> **Best measurement addition**: BSS vs climatology baseline — quantifies "is our pp adding skill at all vs a constant-rate forecast." Can be computed from existing data, no new infra.

Later scoped it in detail: 60 lines of Python, dedicated `analysis/h_pp_climatology_skill.py`, would emit per-lead-band BSS, verdict logic, kill criteria, output shape.

User said go. Started reading similar scripts as templates → discovered `analysis/pp_brier_decomposition.py` line 121:

```python
"brier_skill_vs_climatology": round(1 - brier / uncertainty, 4)
```

**The exact metric I was scoping already existed in a script that runs daily.** Same math (BSS = 1 − Brier/Uncertainty where Uncertainty = obs_bar × (1 − obs_bar), which IS the Brier of the always-guess-base-rate constant forecast).

## Where this is worst

- When user's memory of the codebase is stronger than yours (usually — they built it).
- When you've been in the codebase for many turns and think you know its shape.
- When the metric has a fancy name that makes it feel like new territory ("Brier Skill Score" felt like new work; it's just decomposition arithmetic already computed).

## What good looks like

The two minutes I could have spent BEFORE proposing:

```
grep -rn "brier_skill\|BSS\|climatology" analysis/ | head
```

Would have shown me line 121 of `pp_brier_decomposition.py` immediately. Would have reframed the whole conversation from "let's build this new thing" to "let me pull up the existing numbers."

## Related

- `[[feedback_dont_invent_numbers]]` — sibling: don't fabricate what you can measure.
- `[[feedback_verify_completeness_claims]]` — sibling: verify before asserting.
- `[[feedback_measure_before_concluding]]` — sibling: check state before diagnosing.
