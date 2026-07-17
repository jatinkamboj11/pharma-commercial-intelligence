/* Shared helpers for the dashboard pages. The pages consume the same
   public API (/api/...) that external clients would - the UI is a
   first customer of the API, not a side channel. */

const fmt = new Intl.NumberFormat("en-US");
const money = (v) => "$" + fmt.format(Math.round(v));
const num = (v) => fmt.format(Math.round(v));

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

/* Signature element: 10-cell decile heat strip */
function decileStrip(decile) {
  let cells = "";
  for (let i = 1; i <= 10; i++) {
    let cls = "";
    if (i <= decile) {
      cls = i >= 9 ? "on-high" : i >= 6 ? "on-mid" : "on-low";
    }
    cells += `<i class="${cls}"></i>`;
  }
  return `<span class="strip" role="img" aria-label="decile ${decile} of 10">${cells}</span><span class="decile-num">${decile}</span>`;
}

const chartDefaults = {
  font: { family: "'IBM Plex Mono', monospace", size: 11 },
  ink: "#14282e", soft: "#5b7078", line: "#dde6e7",
  teal: "#0d7a6a", amber: "#d97a1f",
};

function baseChartOpts() {
  return {
    responsive: true,
    plugins: { legend: { labels: { font: chartDefaults.font, color: chartDefaults.ink } } },
    scales: {
      x: { ticks: { font: chartDefaults.font, color: chartDefaults.soft },
           grid: { display: false } },
      y: { ticks: { font: chartDefaults.font, color: chartDefaults.soft },
           grid: { color: chartDefaults.line } },
    },
  };
}
