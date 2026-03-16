/**
 * Plotly chart initialization for HTMX-swapped content.
 */
function initChart(el) {
  const dataAttr = el.getAttribute('data-plotly-data');
  const layoutAttr = el.getAttribute('data-plotly-layout');
  if (!dataAttr) return;

  try {
    const data = JSON.parse(dataAttr);
    const layout = JSON.parse(layoutAttr || '{}');
    // Merge responsive defaults
    layout.autosize = true;
    if (!layout.margin) layout.margin = {l: 40, r: 10, t: 10, b: 40};
    Plotly.newPlot(el, data, layout, {responsive: true, displayModeBar: false});
  } catch (e) {
    console.error('Chart init failed:', e);
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('[data-plotly-data]').forEach(initChart);
});

// Re-initialize after HTMX content swaps
document.body.addEventListener('htmx:afterSwap', function(event) {
  event.detail.target.querySelectorAll('[data-plotly-data]').forEach(initChart);
});
