// ======================================================
// Changelog loader — fetches docs/CHANGELOG.md into the Settings drawer.
//
// HOW_IT_WORKS.md and DATA_PIPELINE.md retired 2026-06-21: nobody read them
// and they drifted from reality. corrections_debug.html is the live canonical
// reference for the math; the README covers the project at the overview level.
// ======================================================

async function loadChangelog() {
  try {
    const response = await fetch('docs/CHANGELOG.md');
    const text = await response.text();
    const html = parseChangelogMarkdown(text);
    document.getElementById('changelogBody').innerHTML = html;
  } catch (err) {
    console.error('Failed to load changelog:', err);
    document.getElementById('changelogBody').innerHTML = '<p style="color:rgba(255,255,255,0.4);">Changelog unavailable</p>';
  }
}

function parseChangelogMarkdown(md) {
  // The file is now mostly HTML: each day-group is wrapped in <details>
  // /<summary> for collapsibility. We pass those through and only transform
  // the remaining inline markdown (bullets, bold, inline code).
  let html = md;

  // Strip the top-level title line.
  html = html.replace(/^# [^\n]*\n+/, '');

  // Inline bullets: `* Foo` → `<li>Foo</li>`.
  html = html.replace(/^\* (.+)$/gm, '<li>$1</li>');

  // Wrap consecutive <li> runs in a styled <ul>.
  html = html.replace(/(<li>[\s\S]+?<\/li>)(?=\n*(?:<\/details>|<details|$))/g,
    '<ul style="margin:6px 0 0 20px;padding:0;list-style:disc;">$1</ul>');

  // Inline bold.
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

  // Inline code.
  html = html.replace(/`([^`]+)`/g, '<code style="background:rgba(255,255,255,0.08);padding:2px 4px;border-radius:3px;font-family:\'SF Mono\',Monaco,monospace;font-size:0.85em;">$1</code>');

  // Style <summary> tags so the day labels read as bold headers.
  html = html.replace(/<summary><strong>([^<]+)<\/strong><\/summary>/g,
    '<summary style="font-weight:900;font-size:1.05em;color:rgba(255,255,255,0.85);cursor:pointer;padding:6px 0;">$1</summary>');

  // Add a little vertical breathing room between collapsibles.
  html = html.replace(/<details( open)?>/g,
    '<details$1 style="margin-bottom:8px;border-bottom:1px solid rgba(255,255,255,0.06);padding-bottom:8px;">');

  return html;
}

// Call on page load
document.addEventListener('DOMContentLoaded', () => {
  loadChangelog();
});
