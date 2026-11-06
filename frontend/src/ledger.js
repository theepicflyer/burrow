import 'vite/modulepreload-polyfill';
import './styles/ledger.css';
import htmx from 'htmx.org';

import { initEntry } from './ledger/entry.js';
import { initToasts } from './ledger/toast.js';
import { initCharts } from './ledger/charts.js';
import { initTheme } from './ledger/theme.js';

window.htmx = htmx;
htmx.config.allowEval = false;
htmx.config.historyCacheSize = 0;

function boot() {
  initTheme();
  initToasts();
  initEntry();
  initCharts(document);
}

document.body.addEventListener('htmx:afterSettle', (e) => initCharts(e.target));

// <select data-reload-param="x">: reload the page with ?x=<value>.
document.addEventListener('change', (e) => {
  const name = e.target.dataset && e.target.dataset.reloadParam;
  if (!name) return;
  const url = new URL(window.location.href);
  url.searchParams.set(name, e.target.value);
  window.location.href = url.toString();
});

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
