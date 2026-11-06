// Category icon picker (templates/ledger/partials/icon_picker.html): search, a live preview,
// and the automatic icon worked out from the name as you type (same rule as apps/ledger/icons.py).
const GENERIC = 'dots-three';

export function guessIcon(name, match) {
  const found = [];
  for (const word of (name.toLowerCase().match(/[a-z]+/g) || [])) {
    const w = match[word] ? word : (word.endsWith('s') && match[word.slice(0, -1)] ? word.slice(0, -1) : null);
    if (w) found.push(match[w]);
  }
  return found.find((i) => i !== GENERIC) || found[0] || '';
}

export function initIconPicker() {
  const root = document.querySelector('[data-icon-picker]');
  if (!root) return;
  const form = root.closest('form');
  const match = JSON.parse(document.getElementById('icon-match').textContent);
  const sprite = root.dataset.sprite;
  const preview = root.querySelector('[data-icon-preview]');
  const label = root.querySelector('[data-icon-label]');
  const hint = root.querySelector('[data-icon-hint]');
  const details = root.querySelector('details');
  const search = root.querySelector('[data-icon-search]');
  const nameInput = form.querySelector('[name=name]');

  function render() {
    const value = form.querySelector('input[name=icon]:checked')?.value || '';
    const kind = form.querySelector('input[name=kind]:checked')?.value || 'budget';
    const name = nameInput.value.trim();
    const icon = value === 'letter' ? '' : value || guessIcon(name, match);
    const tile = document.createElement('span');
    tile.className = `tile${kind === 'fund' ? ' tile--fund' : kind === 'income' ? ' tile--in' : ''}`;
    if (icon) tile.innerHTML = `<svg class="cat-icon" width="22" height="22" aria-hidden="true"><use href="${sprite}#i-${icon}"></use></svg>`;
    else if (kind === 'fund' && value !== 'letter') tile.innerHTML = `<img class="bh-trace" src="${root.dataset.acorn}" width="26" height="26" alt="">`;
    else tile.textContent = (name[0] || '?').toUpperCase();
    preview.replaceChildren(tile);
    const picked = value && value !== 'letter' ? root.querySelector(`input[name=icon][value="${value}"]`)?.closest('[data-l]')?.dataset.l : '';
    label.textContent = value === 'letter' ? 'First letter' : picked || 'Automatic';
    hint.textContent = value ? '' : icon ? 'Picked from the name' : 'Nothing fits the name, so it shows the first letter';
  }

  root.addEventListener('change', (e) => {
    if (e.target.name === 'icon') { render(); details.open = false; }
  });
  form.addEventListener('change', (e) => { if (e.target.name === 'kind') render(); });
  nameInput.addEventListener('input', render);

  search.addEventListener('input', () => {
    const words = search.value.toLowerCase().split(/\s+/).filter(Boolean);
    let any = false;
    root.querySelectorAll('[data-icon-group]').forEach((g) => {
      let shown = 0;
      g.querySelectorAll('[data-k]').forEach((opt) => {
        const ok = words.every((w) => opt.dataset.k.includes(w));
        opt.hidden = !ok;
        if (ok) shown += 1;
      });
      g.hidden = !shown;
      any = any || shown > 0;
    });
    root.querySelector('[data-icon-none]').hidden = any;
  });
  search.addEventListener('keydown', (e) => { if (e.key === 'Enter') e.preventDefault(); });
  render();
}
