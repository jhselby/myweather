---
name: user-skill-level
description: "Joe's self-described coding ability and how he wants Claude to collaborate on code"
metadata: 
  node_type: memory
  type: user
  originSessionId: fa52301e-333a-48b0-9a76-abe4995f3eb6
---

Joe describes his own coding ability as "very low level." He explicitly wants Claude to act as counsel — make the call on technical decisions, explain the reasoning in plain terms, and walk through changes one step at a time rather than dumping a big batch.

Implication for refactors: propose ONE concrete change at a time, explain what's there now and why it's a problem in plain language (not jargon), recommend the fix, and only proceed after Joe agrees. Don't ask Joe to choose between technical options he can't evaluate — pick the right one and tell him why. Don't assume he can spot bugs in proposed code; verify the change yourself by reading the file before and after.
