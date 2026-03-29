// ======================================================
// Changelog loader — fetch and parse CHANGELOG.md
// ======================================================
async function loadChangelog() {
  try {
    const response = await fetch('CHANGELOG.md');
    const text = await response.text();
    const html = parseChangelogMarkdown(text);
    document.getElementById('changelogBody').innerHTML = html;
  } catch (err) {
    console.error('Failed to load changelog:', err);
    document.getElementById('changelogBody').innerHTML = '<p style="color:rgba(255,255,255,0.4);">Changelog unavailable</p>';
  }
}

function parseChangelogMarkdown(md) {
  // Remove title line
  let html = md.replace(/^# .*\n\n/, '');
  
  // Convert ## v3.14 • date to formatted divs
  html = html.replace(/## (v[\d.]+(?:–v[\d.]+)?)\s*•\s*([^\n]+)/g, 
    '<div style="margin-bottom:16px;"><span style="font-weight:900;font-size:1.1em;color:rgba(255,255,255,0.85);">$1</span><span style="color:rgba(255,255,255,0.4);margin-left:8px;">$2</span><ul style="margin:6px 0 0 20px;padding:0;list-style:disc;">');
  
  // Convert * list items to <li>
  html = html.replace(/^\* (.+)$/gm, '<li>$1</li>');
  
  // Close </ul></div> before each new version
  html = html.replace(/<div style=/g, '</ul></div><div style=');
  
  // Fix first entry (no closing tags before it)
  html = html.replace('</ul></div><div', '<div');
  
  // Close final entry
  html += '</ul></div>';
  
  return html;
}

// Call on page load
document.addEventListener('DOMContentLoaded', loadChangelog);
