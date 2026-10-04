---
name: reference-localhost-server
description: Joe always has a local http.server running at http://localhost:8000 on his Mac serving ~/Documents/myweather — use that URL for frontend eyeball testing instead of spinning up a new server on another port.
metadata: 
  node_type: memory
  type: reference
  originSessionId: 11474788-ef32-4445-9527-520896bfadf7
  modified: 2026-09-10T16:14:53.136Z
---

# Localhost server

Joe keeps a persistent Python HTTP server running at **http://localhost:8000** on his Mac serving `~/Documents/myweather`. Any frontend eyeball test (corrections_debug.html, index.html, etc.) should point him there instead of spinning up a new server on another port.

**How to apply:** when Joe needs to eyeball a frontend change per CLAUDE.md §8, hand him the URL directly — e.g. `http://localhost:8000/corrections_debug.html` — and skip the `python3 -m http.server` step. If a different port is ever needed for isolation, ask first.

Told 09-10 after I spun up :8765 for the aggregate-chart eyeball test.
