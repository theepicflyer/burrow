import Chart from 'chart.js/auto';
import {SankeyController, Flow} from 'chartjs-chart-sankey';

Chart.register(SankeyController, Flow);
window.Chart = Chart;

// Burrow chart styling. Colours come from the theme's CSS variables, read when called.
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

window.burrowColors = () => ({
    mint: cssVar('--mint'), sky: cssVar('--sky'), sunny: cssVar('--sunny'), tomato: cssVar('--tomato'),
    bark: cssVar('--bark'), ink: cssVar('--ink'), inkMuted: cssVar('--ink-muted'), line: cssVar('--line'),
    paper: cssVar('--paper'), surface: cssVar('--surface'), mintText: cssVar('--mint-text'), tomatoText: cssVar('--tomato-text'),
});

// Series colours, ordered so neighbours differ in lightness as well as hue.
window.burrowSeries = () => {
    const c = window.burrowColors();
    return [c.mint, c.sky, c.sunny, c.tomato, c.bark, c.inkMuted];
};

// Hex colour + alpha (0-1) -> rgba(), for soft fills under lines.
window.burrowAlpha = (hex, alpha) => {
    const h = hex.replace('#', '');
    const n = parseInt(h.length === 3 ? h.split('').map((x) => x + x).join('') : h, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
};

function applyBurrowChartDefaults() {
    const c = window.burrowColors();
    if (!c.ink) return;
    Chart.defaults.font.family = '"Figtree Variable", system-ui, sans-serif';
    Chart.defaults.color = c.inkMuted;
    Chart.defaults.scale.grid.color = c.line;
    Chart.defaults.scale.border.color = c.line;
    Chart.defaults.elements.line.borderWidth = 3;
    Chart.defaults.elements.bar.borderRadius = 6;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.tooltip.backgroundColor = c.ink;
    Chart.defaults.plugins.tooltip.titleColor = c.paper;
    Chart.defaults.plugins.tooltip.bodyColor = c.paper;
    Chart.defaults.plugins.tooltip.cornerRadius = 10;
    Chart.defaults.plugins.tooltip.padding = 10;
}

// Datasets that bring no colours of their own get the Burrow series (instead of Chart.js' palette).
Chart.register({
    id: 'burrowColors',
    beforeUpdate(chart) {
        const palette = window.burrowSeries();
        if (!palette[0]) return;
        const type = chart.config.type;
        chart.config.data.datasets.forEach((ds, i) => {
            if (ds.borderColor || ds.backgroundColor || ds.colorFrom || ds.colorTo) return;
            if (['pie', 'doughnut', 'polarArea'].includes(ds.type || type)) {
                ds.backgroundColor = ds.data.map((_, j) => palette[j % palette.length]);
                ds.borderColor = window.burrowColors().surface;
                return;
            }
            const color = palette[i % palette.length];
            ds.borderColor = color;
            ds.backgroundColor = ['line', 'radar'].includes(ds.type || type) ? window.burrowAlpha(color, 0.15) : color;
        });
    },
});

applyBurrowChartDefaults();
document.addEventListener('DOMContentLoaded', applyBurrowChartDefaults);
