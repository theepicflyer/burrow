// Burrow toasts: a dark pill with a small animal, one at a time, above the bottom nav.
let current = null;

export function toast(message, { who = 'kacang', mood = 'joy', action = null, ms = 4000 } = {}) {
  const region = document.getElementById('toasts');
  if (!region) return;
  if (current) current.remove();
  const el = document.createElement('div');
  el.className = 'bh-toast';
  el.setAttribute('role', 'status');
  const base = region.dataset.art || '/static/img/burrow/characters/';
  el.innerHTML = `<span class="bh-toast__bub"><img class="bh-mascot" src="${base}${who}-${mood}.svg" width="36" height="36" alt=""></span><span class="bh-toast__text"></span>`;
  el.querySelector('.bh-toast__text').textContent = message;
  if (action) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'bh-btn bh-btn--ghost bh-btn--sm';
    btn.textContent = action.label;
    btn.addEventListener('click', () => { el.remove(); action.run(); });
    el.appendChild(btn);
    ms = Math.max(ms, 6000);
  }
  region.appendChild(el);
  current = el;
  setTimeout(() => { if (el === current) { el.remove(); current = null; } }, ms);
}

// Server-side messages arrive as data-toast elements in the page.
export function initToasts() {
  document.querySelectorAll('[data-toast]').forEach((n) => {
    toast(n.dataset.toast, { mood: n.dataset.mood || 'joy', who: n.dataset.who || 'kacang' });
    n.remove();
  });
}
