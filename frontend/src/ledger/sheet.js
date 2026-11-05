// The add/edit spend sheet. Amount, title, category, save; date, month, note and the rest
// sit behind one "details" row. Any element with [data-add-spend] opens it empty; any element
// with [data-spend='{json}'] opens it to edit that spend.
import { post, changed } from './http.js';
import { toast } from './toast.js';

const $ = (sel, root = document) => root.querySelector(sel);
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const ym = (d) => iso(d).slice(0, 7);
const parseDay = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const addMonths = (d, n) => new Date(d.getFullYear(), d.getMonth() + n, 1);
const monthName = (d, long = false) => d.toLocaleDateString(undefined, { month: long ? 'long' : 'short', ...(long ? {} : {}) });

// "8+4.5" -> 12.5; returns null for anything that isn't a plain sum.
function evaluate(text) {
  const t = text.replace(/\s/g, '').replace(/,/g, '.');
  if (!t) return null;
  if (!/^[-+]?\d*\.?\d+([-+]\d*\.?\d+)*$/.test(t)) return NaN;
  return t.match(/[-+]?\d*\.?\d+/g).reduce((a, b) => a + parseFloat(b), 0);
}

export function initSheet() {
  const sheet = document.getElementById('sheet');
  const dataNode = document.getElementById('ledger-entry');
  if (!sheet || !dataNode) return;
  const data = JSON.parse(dataNode.textContent);
  const cats = new Map(data.cats.map((c) => [String(c.id), c]));
  const today = parseDay(data.today);
  const form = $('#spend-form', sheet);
  const f = {
    amount: $('#f-amount', sheet), calc: $('#f-calc', sheet), amountBox: $('.amount-box', sheet),
    title: $('#f-title', sheet), suggest: $('#f-suggest', sheet), category: $('#f-category', sheet),
    date: $('#f-date', sheet), months: $('#f-months', sheet), note: $('#f-note', sheet),
    refund: $('#f-refund', sheet), repeat: $('#f-repeat', sheet), repeatRow: $('#f-repeat-row', sheet),
    rule: $('#f-rule', sheet), ruleLink: $('#f-rule-link', sheet), summary: $('#f-summary', sheet),
    details: $('#f-details', sheet), toggle: $('.details-toggle', sheet), error: $('#f-error', sheet),
    del: $('#f-delete', sheet), submit: $('#f-submit', sheet), heading: $('#sheet-title', sheet),
  };
  let editing = null; // spend id when editing
  let monthPicked = false; // the user chose a month explicitly
  let catPicked = false;
  let pushed = false;
  let busy = false;

  // ---------- category chips
  const chips = [...sheet.querySelectorAll('[data-cat]')];
  function pickCategory(id, byUser = false) {
    f.category.value = id ? String(id) : '';
    chips.forEach((chip) => {
      const on = chip.dataset.cat === f.category.value;
      chip.classList.toggle('is-selected', on);
      chip.setAttribute('aria-pressed', on ? 'true' : 'false');
      if (on && byUser !== 'quiet') chip.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    });
    if (byUser === true) catPicked = true;
    clearError('category');
  }
  chips.forEach((chip) => chip.addEventListener('click', () => {
    pickCategory(chip.dataset.cat, true);
    if (!f.amount.value) f.amount.focus();
  }));

  // ---------- amount
  function showCalc() {
    const v = f.amount.value;
    const r = evaluate(v);
    f.calc.textContent = /[-+]/.test(v.slice(1)) && Number.isFinite(r) ? `= ${r.toFixed(2)}` : '';
    clearError('amount');
  }
  f.amount.addEventListener('input', showCalc);
  f.amount.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); f.title.focus(); } });

  // ---------- title suggestions
  let matches = [];
  let active = -1;
  function renderSuggest() {
    f.suggest.innerHTML = '';
    if (!matches.length) { f.suggest.hidden = true; return; }
    matches.forEach((m, i) => {
      const li = document.createElement('li');
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', i === active ? 'true' : 'false');
      li.innerHTML = '<span></span><span class="suggest__cat"></span>';
      li.firstChild.textContent = m.t;
      li.lastChild.textContent = cats.get(String(m.c))?.name || '';
      li.addEventListener('mousedown', (e) => { e.preventDefault(); choose(m); });
      f.suggest.appendChild(li);
    });
    f.suggest.hidden = false;
  }
  function choose(m) {
    f.title.value = m.t;
    if (m.c && cats.has(String(m.c))) pickCategory(m.c, 'quiet');
    matches = [];
    renderSuggest();
  }
  f.title.addEventListener('input', () => {
    const q = f.title.value.trim().toLowerCase();
    active = -1;
    if (q.length < 1) { matches = []; renderSuggest(); return; }
    const starts = [], contains = [];
    for (const m of data.titles) {
      const t = m.t.toLowerCase();
      if (t === q) continue;
      if (t.startsWith(q)) starts.push(m); else if (t.includes(q)) contains.push(m);
      if (starts.length >= 6) break;
    }
    matches = starts.concat(contains).slice(0, 6);
    renderSuggest();
    // An exact match picks its usual category unless the user already chose one.
    const exact = data.titles.find((m) => m.t.toLowerCase() === q);
    if (exact && !catPicked && cats.has(String(exact.c))) pickCategory(exact.c, 'quiet');
  });
  f.title.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' && matches.length) { e.preventDefault(); active = (active + 1) % matches.length; renderSuggest(); }
    else if (e.key === 'ArrowUp' && matches.length) { e.preventDefault(); active = (active - 1 + matches.length) % matches.length; renderSuggest(); }
    else if (e.key === 'Escape' && matches.length) { e.stopPropagation(); matches = []; renderSuggest(); }
    else if (e.key === 'Enter') {
      e.preventDefault();
      if (active >= 0 && matches[active]) { choose(matches[active]); return; }
      matches = []; renderSuggest();
      if (f.category.value) form.requestSubmit(); else chips[0]?.focus();
    }
  });
  f.title.addEventListener('blur', () => setTimeout(() => { matches = []; renderSuggest(); }, 100));

  // ---------- date and month
  function renderMonths() {
    const d = f.date.value ? parseDay(f.date.value) : today;
    const own = new Date(d.getFullYear(), d.getMonth(), 1);
    const current = f.months.querySelector('input:checked')?.value;
    const keep = monthPicked ? current : ym(own);
    f.months.innerHTML = '';
    [-1, 0, 1].forEach((n) => {
      const m = addMonths(own, n);
      const id = `f-month-${n + 1}`;
      const label = document.createElement('label');
      label.innerHTML = `<input type="radio" name="month" id="${id}"><span class="bh-chip"></span>`;
      const input = label.firstChild;
      input.value = ym(m);
      input.checked = input.value === keep;
      label.lastChild.textContent = m.getFullYear() === today.getFullYear() ? monthName(m) : `${monthName(m)} ${m.getFullYear()}`;
      input.addEventListener('change', () => { monthPicked = true; renderSummary(); });
      f.months.appendChild(label);
    });
    if (!f.months.querySelector('input:checked')) {
      // A month chosen earlier that is no longer next to the date: fall back to the date's month.
      monthPicked = false;
      f.months.querySelector(`input[value="${ym(own)}"]`).checked = true;
    }
  }
  function renderSummary() {
    const d = f.date.value ? parseDay(f.date.value) : today;
    const diff = Math.round((today - d) / 86400000);
    const day = diff === 0 ? 'Today' : diff === 1 ? 'Yesterday' : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: d.getFullYear() === today.getFullYear() ? undefined : 'numeric' });
    const mv = f.months.querySelector('input:checked')?.value;
    const parts = [day];
    if (mv && mv !== ym(d)) parts.push(`counts toward ${monthName(parseDay(`${mv}-01`), true)}`);
    if (f.note.value.trim()) parts.push('note');
    if (f.refund.checked) parts.push('money back');
    if (f.repeat && f.repeat.value) parts.push(`repeats ${f.repeat.selectedOptions[0].textContent.toLowerCase()}`);
    f.summary.textContent = parts.join(' · ');
    f.amountBox.classList.toggle('is-refund', f.refund.checked);
  }
  f.date.addEventListener('change', () => { renderMonths(); renderSummary(); });
  sheet.querySelectorAll('[data-day]').forEach((b) => b.addEventListener('click', () => {
    const d = new Date(today); d.setDate(d.getDate() - Number(b.dataset.day));
    f.date.value = iso(d); renderMonths(); renderSummary();
  }));
  [f.note, f.refund, f.repeat].forEach((el) => el && el.addEventListener('change', renderSummary));
  f.note.addEventListener('input', renderSummary);

  function setDetails(open) {
    f.details.hidden = !open;
    f.toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  f.toggle.addEventListener('click', () => setDetails(f.details.hidden));

  // ---------- errors
  function clearError(name) {
    const el = sheet.querySelector(`[data-err="${name}"]`);
    if (el) el.textContent = '';
  }
  function showErrors(errors) {
    sheet.querySelectorAll('[data-err]').forEach((el) => { el.textContent = errors[el.dataset.err] || ''; });
    const other = Object.entries(errors).filter(([k]) => !sheet.querySelector(`[data-err="${k}"]`));
    f.error.textContent = other.map(([, v]) => v).join(' ');
    if (errors.date || errors.month || errors.note) setDetails(true);
  }

  // ---------- open / close
  function open(spend) {
    editing = spend ? spend.id : null;
    form.reset();
    showErrors({});
    f.calc.textContent = '';
    monthPicked = false;
    catPicked = !!spend;
    f.heading.textContent = spend ? 'Edit spend' : 'Add spend';
    f.submit.textContent = spend ? 'Save spend' : 'Add spend';
    f.del.hidden = !spend;
    if (f.repeatRow) f.repeatRow.hidden = !!spend;
    f.amount.value = spend ? spend.amount : '';
    f.title.value = spend ? spend.title : '';
    f.date.value = spend ? spend.date : iso(today);
    f.note.value = spend ? spend.note : '';
    f.refund.checked = spend ? spend.refund : false;
    pickCategory(spend ? spend.category : null, 'quiet');
    renderMonths();
    if (spend) {
      const want = spend.month;
      const radio = f.months.querySelector(`input[value="${want}"]`);
      if (radio) { radio.checked = true; monthPicked = want !== spend.date.slice(0, 7); }
    }
    f.rule.hidden = !(spend && spend.recurring);
    if (spend && spend.recurring) {
      f.ruleLink.textContent = spend.recurring_title || 'recurring spend';
      f.ruleLink.href = `${f.ruleLink.dataset.base}${spend.recurring}/`;
    }
    renderSummary();
    setDetails(!!spend && (spend.note || spend.refund || spend.month !== spend.date.slice(0, 7)));
    sheet.hidden = false;
    document.documentElement.style.overflow = 'hidden';
    if (!pushed) { history.pushState({ sheet: true }, ''); pushed = true; }
    // Focus inside the opening tap so phones raise the keyboard.
    f.amount.focus({ preventScroll: true });
    if (spend) f.amount.select();
  }
  function close({ fromPop = false } = {}) {
    if (sheet.hidden) return;
    sheet.hidden = true;
    document.documentElement.style.overflow = '';
    matches = []; renderSuggest();
    if (pushed && !fromPop) { pushed = false; history.back(); }
    pushed = false;
  }
  window.addEventListener('popstate', () => { if (!sheet.hidden) close({ fromPop: true }); });
  sheet.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => close()));
  sheet.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });

  document.addEventListener('click', (e) => {
    const adder = e.target.closest('[data-add-spend]');
    if (adder) { e.preventDefault(); open(null); if (adder.dataset.category) pickCategory(adder.dataset.category, true); return; }
    const row = e.target.closest('[data-spend]');
    if (row) { e.preventDefault(); open(JSON.parse(row.dataset.spend)); }
  });

  // ---------- save / delete / undo
  function payload() {
    const fd = new FormData(form);
    const r = evaluate(f.amount.value);
    if (Number.isFinite(r)) fd.set('amount', r.toFixed(2));
    if (!f.refund.checked) fd.delete('refund');
    return fd;
  }
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (busy) return;
    const errors = {};
    const r = evaluate(f.amount.value);
    if (r === null) errors.amount = 'Enter an amount.';
    else if (!Number.isFinite(r) || r === 0) errors.amount = 'Enter an amount like 12.50.';
    if (!f.category.value) errors.category = 'Pick a category.';
    if (Object.keys(errors).length) { showErrors(errors); (errors.amount ? f.amount : chips[0])?.focus(); return; }
    busy = true; f.submit.disabled = true;
    try {
      const url = editing ? sheet.dataset.update.replace('/0/', `/${editing}/`) : sheet.dataset.create;
      const res = await post(url, payload());
      if (!res.ok) { showErrors(res.errors || {}); return; }
      close();
      changed();
      toast(res.toast, {
        action: res.undo ? { label: 'Undo', run: () => undoCreate(res.undo) } : null,
      });
    } catch (err) {
      f.error.textContent = "Couldn't save. Check your connection and try again.";
    } finally {
      busy = false; f.submit.disabled = false;
    }
  });
  async function undoCreate(url) {
    try { await post(url, {}); changed(); toast('Spend removed', { mood: 'happy' }); }
    catch (_) { toast("Couldn't undo. Delete it from the list instead.", { mood: 'worried' }); }
  }
  f.del.addEventListener('click', async () => {
    if (!editing || busy) return;
    busy = true;
    try {
      const res = await post(sheet.dataset.delete.replace('/0/', `/${editing}/`), {});
      close();
      changed();
      const s = res.spend;
      toast(res.toast, {
        mood: 'happy',
        action: { label: 'Undo', run: async () => {
          await post(sheet.dataset.create, { amount: s.amount, refund: s.refund ? 'on' : null, title: s.title, category: s.category, date: s.date, month: s.month, note: s.note });
          changed();
        } },
      });
    } catch (_) {
      f.error.textContent = "Couldn't delete. Check your connection and try again.";
    } finally { busy = false; }
  });

  // PWA shortcut / deep link: /?add=1 opens the sheet.
  if (new URLSearchParams(location.search).has('add')) open(null);
}
