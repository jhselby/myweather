---
name: feedback-check-code-before-architectural-claims
description: "Before framing 'we should build X' or 'the current system is only Y' — read the code first. Claude's default is to describe architecture from memory and then propose extensions, when the extension is often already wired. Documented 09-25: claimed the L1 selector was 'a 32-state lookup' and proposed building a router, when l1_selector.py already had 5 mechanisms including a shipped-but-thin per-obs classifier."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: db0e0f7d-96cd-471b-a038-fb5297164147
  modified: 2026-09-26T10:18:37.392Z
---

# Rule

Before saying **"we should build X"** or **"the current system is only Y"** for any project-owned mechanism, read the file first — not a grep, an actual Read. Model claims from memory are drift-prone.

**Why:** 09-25. In a strategic reframing conversation I described the L1 selector as "a 32-state lookup masquerading as a routing decision" and framed the plan as "build a per-obs classifier that consumes all available features, ship as THE selector." Joe pushed back: "It's 7 or eight weeks, no way we only have a simple 32 rule something or other. That's impossible after the amount of time we've worked on this." Reading `weather_collector/processors/l1_selector.py` showed 5 wired mechanisms — base table, regime overrides, `_LEARNED_CELLS` per-obs classifier (`_learned_predict` sigmoid over 12 features, since v0.6.644), `_IMS_SELECTOR_CELLS` hardcoded threshold, `_BLENDER_CELLS` ω blend. The "router" I was proposing to build was already shipped in code with `LEARNED_SELECTOR_SHADOW_ENABLED = False` and a thin curated JSON.

The reframe on top of that discovery — fill the wired mechanism vs. build a new one — is a much sharper plan than what I was proposing. Reading code before framing would have led there directly.

**How to apply:**

- Any time the topic is "the current system does X, we should add Y," and Y sounds like a general infrastructure addition, `grep`/`Read` the module before saying it. What's already there is often 60-80% of the proposal.
- Especially for `weather_collector/processors/*.py` and `analysis/*.py` — those have accumulated infrastructure that memory doesn't fully track. Check code, not memory.
- If a memory says "we have a table for X, wired but thin" (see [[project_router_as_authority_pivot]]), that's a signal the code path is more built out than a shadow-experiment framing would suggest.

Related: [[feedback_refresh_current_state_before_defending]], [[feedback_stated_intent_vs_code_behavior]].
