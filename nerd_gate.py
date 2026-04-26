#!/usr/bin/env python3
"""Reorganize settings modal: Theme + Version visible, rest behind nerd gate"""

with open("index.html", "rb") as f:
    c = f.read().decode()

old = '''        <!-- Changelog -->
        <div class="modal-setting-group">
          <div id="changelogToggle" onclick="document.getElementById('changelogBody').style.display=document.getElementById('changelogBody').style.display==='none'?'block':'none'"
               style="font-size:0.85rem;font-weight:700;color:var(--muted);cursor:pointer;user-select:none;">
            Changelog ▾
          </div>
          <div id="changelogBody" style="display:none;font-size:0.8rem;line-height:1.7;color:var(--muted);max-height:260px;overflow-y:auto;margin-top:8px;"></div>
        </div>
        <!-- Data Pipeline -->
        <div class="modal-setting-group">
          <div id="dataPipelineToggle" onclick="document.getElementById('dataPipelineBody').style.display=document.getElementById('dataPipelineBody').style.display==='none'?'block':'none'"
               style="font-size:0.85rem;font-weight:700;color:var(--muted);cursor:pointer;user-select:none;">
            Data Pipeline Reference ▾
          </div>
          <div id="dataPipelineBody" style="display:none;font-size:0.8rem;line-height:1.7;color:var(--muted);max-height:400px;overflow-y:auto;margin-top:8px;"></div>
        </div>
        <!-- Data Sources -->
        <div class="modal-setting-group">
          <div id="sourcesToggle" onclick="document.getElementById('sourcesBody').style.display=document.getElementById('sourcesBody').style.display==='none'?'block':'none'"
               style="font-size:0.85rem;font-weight:700;color:var(--muted);cursor:pointer;user-select:none;">
            Data Sources ▾
          </div>
          <div id="sourcesBody" style="display:none;margin-top:8px;">
            <div id="sourcesTableModal"></div>
          </div>
        </div>
        <!-- Data timestamps -->
        <div class="modal-setting-group" style="border-top:1px solid var(--border);padding-top:16px;margin-top:8px;">
          <div class="modal-setting-label" style="margin-bottom:8px;">Data Info</div>
          <div style="font-size:0.82rem;color:var(--muted);display:flex;flex-direction:column;gap:4px;">
            <div>Data generated: <span id="dataUpdated2">--</span></div>
            <div>Code loaded: <span id="pageLoaded2">--</span></div>
          </div>
        </div>'''

new = '''        <!-- Nerd Stuff gate -->
        <div class="modal-setting-group" style="border-top:1px solid var(--border);padding-top:16px;margin-top:8px;">
          <div onclick="var b=document.getElementById('nerdStuffBody');b.style.display=b.style.display==='none'?'block':'none'"
               style="font-size:0.85rem;font-weight:700;color:var(--muted);cursor:pointer;user-select:none;">
            Nerd Stuff ▾
          </div>
          <div id="nerdStuffBody" style="display:none;margin-top:12px;">
            <!-- Changelog -->
            <div class="modal-setting-group">
              <div id="changelogToggle" onclick="event.stopPropagation();document.getElementById('changelogBody').style.display=document.getElementById('changelogBody').style.display==='none'?'block':'none'"
                   style="font-size:0.85rem;font-weight:700;color:var(--muted);cursor:pointer;user-select:none;">
                Changelog ▾
              </div>
              <div id="changelogBody" style="display:none;font-size:0.8rem;line-height:1.7;color:var(--muted);max-height:260px;overflow-y:auto;margin-top:8px;"></div>
            </div>
            <!-- Data Pipeline -->
            <div class="modal-setting-group">
              <div id="dataPipelineToggle" onclick="event.stopPropagation();document.getElementById('dataPipelineBody').style.display=document.getElementById('dataPipelineBody').style.display==='none'?'block':'none'"
                   style="font-size:0.85rem;font-weight:700;color:var(--muted);cursor:pointer;user-select:none;">
                Data Pipeline Reference ▾
              </div>
              <div id="dataPipelineBody" style="display:none;font-size:0.8rem;line-height:1.7;color:var(--muted);max-height:400px;overflow-y:auto;margin-top:8px;"></div>
            </div>
            <!-- Data Sources -->
            <div class="modal-setting-group">
              <div id="sourcesToggle" onclick="event.stopPropagation();document.getElementById('sourcesBody').style.display=document.getElementById('sourcesBody').style.display==='none'?'block':'none'"
                   style="font-size:0.85rem;font-weight:700;color:var(--muted);cursor:pointer;user-select:none;">
                Data Sources ▾
              </div>
              <div id="sourcesBody" style="display:none;margin-top:8px;">
                <div id="sourcesTableModal"></div>
              </div>
            </div>
            <!-- Licenses -->
            <div class="modal-setting-group">
              <div onclick="event.stopPropagation();document.getElementById('licensesBody').style.display=document.getElementById('licensesBody').style.display==='none'?'block':'none'"
                   style="font-size:0.85rem;font-weight:700;color:var(--muted);cursor:pointer;user-select:none;">
                Licenses ▾
              </div>
              <div id="licensesBody" style="display:none;font-size:0.8rem;line-height:1.7;color:var(--muted);margin-top:8px;">
                <strong>SunCalc 1.9.0</strong> — BSD-2-Clause<br>
                <strong>Leaflet 1.9.4</strong> — BSD-2-Clause<br>
                <strong>Chart.js 4.4.4</strong> — MIT
              </div>
            </div>
            <!-- Data timestamps -->
            <div class="modal-setting-group" style="border-top:1px solid var(--border);padding-top:12px;margin-top:8px;">
              <div class="modal-setting-label" style="margin-bottom:8px;">Data Info</div>
              <div style="font-size:0.82rem;color:var(--muted);display:flex;flex-direction:column;gap:4px;">
                <div>Data generated: <span id="dataUpdated2">--</span></div>
                <div>Code loaded: <span id="pageLoaded2">--</span></div>
              </div>
            </div>
          </div>
        </div>'''

if old in c:
    c = c.replace(old, new)
    with open("index.html", "wb") as f:
        f.write(c.encode())
    print("SUCCESS")
else:
    print("ERROR: old block not found")
