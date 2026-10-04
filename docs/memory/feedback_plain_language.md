---
name: feedback-plain-language
description: "App UI must use plain English — no weather jargon, NWS terminology, or technical labels visible to users"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f73ef82b-b9fa-4a7b-b4ac-3975805e79b2
---

Every label, badge, row value, and status in the app must be readable by a person who knows nothing about meteorology.

**Why:** Joe caught multiple instances of jargon leaking into the UI: "Watch" (NWS severity term), "Atmospheric Instability (CAPE)", "atmosphere slightly unstable", "Weak" (CAPE category). Users just want to know if something matters and how much.

**How to apply:**
- Never use NWS severity vocabulary ("Watch", "Advisory", "Warning") as UI labels for app-generated content — those terms belong only to official NWS alerts
- Replace technical labels with plain risk/outcome language: "Low Risk", "Moderate Risk", "High Risk" not "Weak", "Watch", "CAPE 671 J/kg"
- Technical details (J/kg values, CAPE explanation) belong in footnotes only — never as primary display values
- Ask: "would someone's grandparent understand this without googling it?" If not, rewrite it
- Watch For section is for things that actually warrant attention — don't show "Low Risk" items there; threshold should be Moderate+ or Active/Severe
