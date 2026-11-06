// Charts are declared in templates as <canvas data-chart="kind" data-src="json-script-id">.
// Chart.js loads only on pages that have one, so the entry flow stays light.
let ChartLib = null;

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const colors = () => ({
  mint: cssVar('--mint'), sky: cssVar('--sky'), sunny: cssVar('--sunny'), tomato: cssVar('--tomato'),
  bark: cssVar('--bark'), ink: cssVar('--ink'), muted: cssVar('--ink-muted'), line: cssVar('--line'),
  paper: cssVar('--paper'), surface: cssVar('--surface'), sunk: cssVar('--surface-sunk'),
});
const alpha = (hex, a) => {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((x) => x + x).join('') : h, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};

async function lib() {
  if (ChartLib) return ChartLib;
  const mod = await import('chart.js/auto');
  ChartLib = mod.default;
  const c = colors();
  const d = ChartLib.defaults;
  d.font.family = '"Figtree Variable", system-ui, sans-serif';
  d.color = c.muted;
  d.scale.grid.color = c.line;
  d.scale.border.color = c.line;
  d.elements.line.borderWidth = 3;
  d.elements.bar.borderRadius = 6;
  d.maintainAspectRatio = false;
  d.plugins.legend.labels.usePointStyle = true;
  d.plugins.tooltip.backgroundColor = c.ink;
  d.plugins.tooltip.titleColor = c.paper;
  d.plugins.tooltip.bodyColor = c.paper;
  d.plugins.tooltip.cornerRadius = 10;
  d.plugins.tooltip.padding = 10;
  return ChartLib;
}

const money = (symbol) => (v) => `${v < 0 ? '\u2212' : ''}${symbol}${Math.abs(Number(v)).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

function budgetVsSpent(data, c, symbol) {
  // Bars: spent (tomato when over, faded while the month is running). Line: budget.
  const over = data.spent.map((s, i) => s > data.budget[i]);
  const partial = data.partial || data.spent.map(() => false);
  return {
    type: 'bar',
    data: {
      labels: data.labels,
      datasets: [
        {
          type: 'line', label: 'Budget', data: data.budget, borderColor: c.ink, backgroundColor: c.ink,
          borderDash: [6, 5], borderWidth: 2, pointRadius: 0, stepped: 'middle', order: 0,
        },
        {
          label: 'Spent', data: data.spent, order: 1,
          backgroundColor: data.spent.map((_, i) => alpha(over[i] ? c.tomato : c.mint, partial[i] ? 0.45 : 1)),
          borderColor: c.ink, borderWidth: 0,
        },
      ],
    },
    options: {
      interaction: { mode: 'index', intersect: false },
      scales: { y: { beginAtZero: true, ticks: { callback: money(symbol) } }, x: { grid: { display: false } } },
      plugins: {
        legend: { display: false }, // the card header carries a legend that explains the colours
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${money(symbol)(ctx.parsed.y)}` } },
      },
    },
  };
}

function fundLines(data, c, symbol) {
  const series = [c.mint, c.sky, c.sunny, c.tomato, c.bark, c.muted];
  return {
    type: 'line',
    data: {
      labels: data.labels,
      datasets: data.funds.map((f, i) => ({
        label: f.name, data: f.values, borderColor: series[i % series.length],
        backgroundColor: series[i % series.length], pointRadius: 0, tension: 0.25,
      })),
    },
    options: {
      interaction: { mode: 'index', intersect: false },
      scales: { y: { ticks: { callback: money(symbol) } }, x: { grid: { display: false } } },
      plugins: { tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${money(symbol)(ctx.parsed.y)}` } } },
    },
  };
}

function fundHistory(data, c, symbol) {
  return {
    type: 'bar',
    data: {
      labels: data.labels,
      datasets: [
        { type: 'line', label: 'Balance', data: data.balance, borderColor: c.mint, backgroundColor: alpha(c.mint, 0.15), fill: true, pointRadius: 0, tension: 0.25, order: 0 },
        { label: 'Spent', data: data.spent, backgroundColor: alpha(c.bark, 0.8), order: 1 },
      ],
    },
    options: {
      interaction: { mode: 'index', intersect: false },
      scales: { y: { beginAtZero: true, ticks: { callback: money(symbol) } }, x: { grid: { display: false } } },
    },
  };
}

function inOut(data, c, symbol) {
  // Income against everything spent (budgets and funds), faded while the month is running.
  const partial = data.partial || data.income.map(() => false);
  return {
    type: 'bar',
    data: {
      labels: data.labels,
      datasets: [
        { label: 'Income', data: data.income, backgroundColor: data.income.map((_, i) => alpha(c.mint, partial[i] ? 0.45 : 1)) },
        { label: 'Spent', data: data.out, backgroundColor: data.out.map((_, i) => alpha(c.bark, partial[i] ? 0.45 : 1)) },
      ],
    },
    options: {
      interaction: { mode: 'index', intersect: false },
      scales: { y: { beginAtZero: true, ticks: { callback: money(symbol) } }, x: { grid: { display: false } } },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${money(symbol)(ctx.parsed.y)}` } } },
    },
  };
}

function received(data, c, symbol) {
  return {
    type: 'bar',
    data: { labels: data.labels, datasets: [{ label: 'Received', data: data.received, backgroundColor: c.mint }] },
    options: {
      scales: { y: { beginAtZero: true, ticks: { callback: money(symbol) } }, x: { grid: { display: false } } },
      plugins: { legend: { display: false } },
    },
  };
}

const KINDS = { budget: budgetVsSpent, funds: fundLines, fund: fundHistory, inout: inOut, income: received };

export async function initCharts(root) {
  const canvases = (root || document).querySelectorAll('canvas[data-chart]');
  if (!canvases.length) return;
  const Chart = await lib();
  const c = colors();
  canvases.forEach((canvas) => {
    const src = document.getElementById(canvas.dataset.src);
    const build = KINDS[canvas.dataset.chart];
    if (!src || !build) return;
    Chart.getChart(canvas)?.destroy();
    const symbol = "$";
    new Chart(canvas, build(JSON.parse(src.textContent), c, symbol));
  });
}
