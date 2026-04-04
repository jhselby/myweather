// ======================================================
// Documentation loaders — fetch and parse markdown docs
// ======================================================

// Load changelog from docs/CHANGELOG.md
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

// Load data pipeline documentation from docs/DATA_PIPELINE.md
async function loadDataPipeline() {
  try {
    const response = await fetch('docs/DATA_PIPELINE.md');
    const text = await response.text();
    const html = parseDataPipelineMarkdown(text);
    document.getElementById('dataPipelineBody').innerHTML = html;
  } catch (err) {
    console.error('Failed to load data pipeline docs:', err);
    document.getElementById('dataPipelineBody').innerHTML = '<p style="color:rgba(255,255,255,0.4);">Documentation unavailable</p>';
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

function parseDataPipelineMarkdown(md) {
  // Simple markdown parser for technical documentation
  let html = md;
  
  // Convert # headers to styled divs
  html = html.replace(/^# (.+)$/gm, '<div style="font-size:1.3em;font-weight:900;color:rgba(255,255,255,0.95);margin:16px 0 8px 0;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:4px;">$1</div>');
  html = html.replace(/^## (.+)$/gm, '<div style="font-size:1.1em;font-weight:800;color:rgba(255,255,255,0.85);margin:14px 0 6px 0;">$1</div>');
  html = html.replace(/^### (.+)$/gm, '<div style="font-size:0.95em;font-weight:700;color:rgba(255,255,255,0.75);margin:10px 0 4px 0;">$1</div>');
  
  // Convert **bold** and *italic*
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong style="color:rgba(255,255,255,0.9);">$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  
  // Convert `code` to styled spans
  html = html.replace(/`([^`]+)`/g, '<code style="background:rgba(255,255,255,0.08);padding:2px 4px;border-radius:3px;font-family:\'SF Mono\',Monaco,monospace;font-size:0.9em;">$1</code>');
  
  // Convert code blocks ```language\ncode\n``` to styled pre
  html = html.replace(/```(\w+)?\n([\s\S]+?)```/g, '<pre style="background:rgba(0,0,0,0.3);padding:10px;border-radius:4px;overflow-x:auto;margin:8px 0;font-family:\'SF Mono\',Monaco,monospace;font-size:0.85em;line-height:1.4;"><code>$2</code></pre>');
  
  // Convert bullet lists
  html = html.replace(/^- (.+)$/gm, '<li style="margin-left:20px;">$1</li>');
  html = html.replace(/^\* (.+)$/gm, '<li style="margin-left:20px;">$1</li>');
  
  // Convert tables (simple parser - works for | header | rows |)
  html = html.replace(/\|(.+)\|\n\|[-:\s|]+\|\n((?:\|.+\|\n?)+)/g, function(match, header, rows) {
    let tableHtml = '<table style="width:100%;border-collapse:collapse;margin:10px 0;font-size:0.85em;">';
    tableHtml += '<thead><tr style="border-bottom:2px solid rgba(255,255,255,0.2);">';
    header.split('|').filter(h => h.trim()).forEach(h => {
      tableHtml += `<th style="padding:6px;text-align:left;font-weight:700;">${h.trim()}</th>`;
    });
    tableHtml += '</tr></thead><tbody>';
    rows.trim().split('\n').forEach(row => {
      if (row.trim()) {
        tableHtml += '<tr style="border-bottom:1px solid rgba(255,255,255,0.1);">';
        row.split('|').filter(c => c.trim()).forEach(cell => {
          tableHtml += `<td style="padding:6px;">${cell.trim()}</td>`;
        });
        tableHtml += '</tr>';
      }
    });
    tableHtml += '</tbody></table>';
    return tableHtml;
  });
  
  // Convert newlines to <br> for paragraphs
  html = html.replace(/\n\n/g, '<br><br>');
  
  return html;
}

// Call on page load
document.addEventListener('DOMContentLoaded', () => {
  loadChangelog();
  loadDataPipeline();
});
