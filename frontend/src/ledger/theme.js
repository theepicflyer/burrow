// Theme: "system" (default) follows the device; "light"/"dark" stick. Set early by an inline
// script in <head>; this wires the switches.
const KEY = 'burrow-theme';

export function applyTheme(choice) {
  const dark = choice === 'dark' || (choice !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'wygiwyh_dark' : 'wygiwyh_light';
}

export function initTheme() {
  let choice = 'system';
  try { choice = localStorage.getItem(KEY) || 'system'; } catch (_) { /* storage blocked */ }
  document.querySelectorAll('input[name=theme]').forEach((input) => {
    input.checked = input.value === choice;
    input.addEventListener('change', () => {
      try { localStorage.setItem(KEY, input.value); } catch (_) { /* ignore */ }
      applyTheme(input.value);
      window.location.reload(); // charts read colours at draw time
    });
  });
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    let c = 'system';
    try { c = localStorage.getItem(KEY) || 'system'; } catch (_) { /* ignore */ }
    if (c === 'system') window.location.reload();
  });
}
