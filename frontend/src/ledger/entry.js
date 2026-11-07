// The add/edit transaction flow (templates/ledger/partials/entry.html).
// New: amount → title → category → review. Each page fits above the phone keyboard and
// moves on by itself where it can: Return on the title, a tap on a suggestion or a category.
// Any element with [data-add-spend] opens it empty; [data-spend='{json}'] opens it to edit.
import { post, changed } from './http.js';
import { toast } from './toast.js';

const MAIN = ['amount', 'title', 'category', 'review'];
const pad = (n) => String(n).padStart(2, '0');
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const ym = (d) => iso(d).slice(0, 7);
const parseDay = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d || 1); };
const addMonths = (d, n) => new Date(d.getFullYear(), d.getMonth() + n, 1);
const monthName = (d, long) => d.toLocaleDateString(undefined, { month: long ? 'long' : 'short' });
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const iconSvg = (sprite, name, size = 18) => (name ? `<svg class="cat-icon" width="${size}" height="${size}" aria-hidden="true"><use href="${sprite}#i-${name}"></use></svg>` : '');
const money = (v) => `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export function initEntry() {
  const root = document.getElementById('entry');
  const dataNode = document.getElementById('ledger-entry');
  if (!root || !dataNode) return;
  const data = JSON.parse(dataNode.textContent);
  const cats = new Map(data.cats.map((c) => [String(c.id), c]));
  const today = parseDay(data.today);
  const $ = (sel) => root.querySelector(sel);
  const pages = Object.fromEntries([...root.querySelectorAll('[data-page]')].map((p) => [p.dataset.page, p]));
  const el = {
    panel: $('.entry__panel'), dots: [...root.querySelectorAll('.entry__dots span')], summary: $('#entry-summary'),
    back: $('[data-back]'), amount: $('#entry-amount'), amountNext: $('[data-next="amount"]'),
    title: $('#entry-title'), suggest: $('#entry-suggest'), hint: $('#entry-title-hint'),
    catGrid: $('#entry-cats'), catBack: $('#entry-cats-back'),
    heroAmount: $('.entry__hero-amount'), heroTitle: $('.entry__hero-title'), heroCat: $('.entry__hero-cat'),
    heroTile: $('#entry-hero-tile'), heroCatName: $('#entry-hero-cat-name'), heroCatKind: $('#entry-hero-cat-kind'),
    dateOther: $('#entry-date-other'), monthOpts: $('#entry-month-opts'), noteValue: $('#entry-note-value'),
    repeatField: $('#entry-repeat-field'), rule: $('#entry-rule'),
    ruleLink: $('#entry-rule-link'), error: $('#entry-error'), save: $('#entry-save'), del: $('#entry-delete'),
    calTitle: $('#entry-cal-title'), cal: $('#entry-cal'), months: $('#entry-months'), note: $('#entry-note'),
  };
  // The category label sits inside the grid so CSS order can put it between groups.
  el.catGrid.appendChild(el.catBack);
  const dateOtherHtml = el.dateOther.innerHTML; // calendar icon + "Other"

  let s = null; // the transaction being entered
  let page = 'amount';
  let trail = []; // pages to go back through
  let calView = null;
  let busy = false;
  let pushed = false;

  // ---------- amount (own numpad, so no keyboard here)
  const amountValue = () => Number(`${s.int || '0'}.${s.dec || '0'}`);
  function renderAmount() {
    const int = Number(s.int || '0').toLocaleString(undefined);
    el.amount.textContent = s.hasDec ? `${int}.${s.dec}` : int;
    el.amount.parentElement.classList.toggle('is-empty', amountValue() === 0);
    el.amountNext.disabled = amountValue() <= 0;
  }
  function key(k) {
    if (k === 'back') {
      if (s.dec) s.dec = s.dec.slice(0, -1);
      else if (s.hasDec) s.hasDec = false;
      else s.int = s.int.slice(0, -1);
    } else if (k === '.') {
      s.hasDec = true;
    } else if (s.hasDec) {
      if (s.dec.length < 2) s.dec += k;
    } else if (s.int.length < 9) {
      s.int = s.int === '0' ? k : s.int + k;
    }
    if (navigator.vibrate) try { navigator.vibrate(5); } catch (_) { /* unsupported */ }
    renderAmount();
  }
  root.querySelectorAll('[data-key]').forEach((b) => b.addEventListener('click', () => key(b.dataset.key)));

  function setType(type) {
    s.type = type;
    root.querySelectorAll('[data-type]').forEach((b) => {
      const on = b.dataset.type === type;
      b.classList.toggle('is-on', on);
      b.setAttribute('aria-checked', on ? 'true' : 'false');
    });
    root.querySelectorAll('[data-q-expense]').forEach((q) => { q.textContent = q.dataset[type === 'income' ? 'qIncome' : 'qExpense']; });
    el.title.placeholder = type === 'income' ? 'e.g. Salary' : 'e.g. Chicken rice';
    root.classList.toggle('is-income', type === 'income');
    // Income first (then the budgets and funds it can be money back to); expenses never go to income.
    let incomeSeen = false;
    root.querySelectorAll('[data-cat]').forEach((t) => {
      const income = t.dataset.kind === 'income';
      incomeSeen = incomeSeen || income;
      t.hidden = type === 'expense' && income;
      t.style.order = type === 'income' ? (income ? 0 : 2) : 0;
    });
    el.catBack.hidden = type !== 'income' || !incomeSeen;
    el.catBack.style.order = 1;
    if (s.category && type === 'expense' && cats.get(String(s.category))?.kind === 'income') s.category = null;
  }
  root.querySelectorAll('[data-type]').forEach((b) => b.addEventListener('click', () => { setType(b.dataset.type); renderSummary(); }));

  // ---------- title and its suggestions
  function suggestions() {
    const q = el.title.value.trim().toLowerCase();
    const want = (m) => (m.y || 'expense') === s.type && cats.has(String(m.c));
    const out = [];
    for (const m of data.titles) {
      if (!want(m)) continue;
      const t = m.t.toLowerCase();
      if (!q || t.startsWith(q)) out.push(m);
      if (out.length >= 8) break;
    }
    if (q && out.length < 8) {
      for (const m of data.titles) {
        if (want(m) && !m.t.toLowerCase().startsWith(q) && m.t.toLowerCase().includes(q)) out.push(m);
        if (out.length >= 8) break;
      }
    }
    return out;
  }
  function renderSuggest() {
    const list = suggestions();
    el.suggest.innerHTML = list.map((m, i) =>
      `<li><button type="button" data-suggest="${i}"><span>${esc(m.t)}</span><span class="entry__suggest-cat">${iconSvg(data.sprite, cats.get(String(m.c))?.icon)}${esc(cats.get(String(m.c))?.name || '')}</span></button></li>`).join('');
    el.suggest.querySelectorAll('[data-suggest]').forEach((b) => {
      // pointerdown keeps the keyboard from bouncing before the page changes
      b.addEventListener('pointerdown', (e) => e.preventDefault());
      b.addEventListener('click', () => {
        const m = list[Number(b.dataset.suggest)];
        s.title = m.t;
        el.title.value = m.t;
        s.category = m.c;
        after('review');
      });
    });
    el.hint.hidden = !list.length;
  }
  el.title.addEventListener('input', () => { s.title = el.title.value; renderSuggest(); });
  el.title.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); titleDone(); }
  });
  function titleDone() {
    s.title = el.title.value.trim();
    // An exact match to a past title brings its category along.
    const exact = data.titles.find((m) => m.t.toLowerCase() === s.title.toLowerCase() && (m.y || 'expense') === s.type && cats.has(String(m.c)));
    if (exact && !s.category) s.category = exact.c;
    after(s.category ? 'review' : 'category');
  }

  // ---------- category
  root.querySelectorAll('[data-cat]').forEach((b) => b.addEventListener('click', () => {
    s.category = Number(b.dataset.cat);
    markCategory();
    setTimeout(() => after('review'), 140);
  }));
  function markCategory() {
    root.querySelectorAll('[data-cat]').forEach((b) => b.classList.toggle('is-on', String(b.dataset.cat) === String(s.category)));
  }

  // ---------- review and its detail pages
  function dayLabel(d) {
    const diff = Math.round((today - d) / 86400000);
    if (diff === 0) return 'Today';
    if (diff === 1) return 'Yesterday';
    return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: d.getFullYear() === today.getFullYear() ? undefined : 'numeric' });
  }
  const kindLabels = { budget: 'Budget', fund: 'Sinking fund', income: 'Income' };
  // Long name this year, "Sep 2025" otherwise, so it fits a third of the row.
  const monthLabel = (m) => (m.getFullYear() === today.getFullYear() ? monthName(m, true) : `${monthName(m)} ${m.getFullYear()}`);
  const radio = (b, on) => { b.classList.toggle('is-on', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); };
  const daysAgo = (d) => Math.round((today - d) / 86400000);
  function renderReview() {
    const income = s.type === 'income';
    el.heroAmount.textContent = `${income ? '+' : '−'}${money(amountValue())}`;
    el.heroAmount.classList.toggle('in-text', income);
    el.heroTitle.textContent = s.title || cats.get(String(s.category))?.name || 'Add a title';
    el.heroTitle.classList.toggle('muted', !s.title);
    const cat = cats.get(String(s.category));
    // The same tile the category grid draws (icon, acorn or letter).
    const tile = cat && el.catGrid.querySelector(`[data-cat="${cat.id}"] .tile`);
    el.heroTile.innerHTML = tile ? tile.outerHTML : '';
    el.heroTile.hidden = !tile;
    el.heroCatName.textContent = cat ? cat.name : 'Pick a category';
    el.heroCatKind.textContent = cat ? (cat.kind !== 'income' && income ? `${kindLabels[cat.kind]} · money back` : kindLabels[cat.kind] || '') : '';
    el.heroCat.classList.toggle('is-missing', !cat);
    // Date: three recent days, else "Other" shows the picked date.
    const ago = daysAgo(s.date);
    root.querySelectorAll('#entry-dates [data-day-ago]').forEach((b) => radio(b, Number(b.dataset.dayAgo) === ago));
    const otherDate = ago < 0 || ago > 2;
    radio(el.dateOther, otherDate);
    el.dateOther.innerHTML = otherDate
      ? esc(s.date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: s.date.getFullYear() === today.getFullYear() ? undefined : '2-digit' }))
      : dateOtherHtml;
    // Month: the date's month and the one before (a late bill), else "Other" shows the picked month.
    const own = new Date(s.date.getFullYear(), s.date.getMonth(), 1);
    const near = [addMonths(own, -1), own];
    const otherMonth = !near.some((m) => ym(m) === s.month);
    const opt = (on, attr, label) => `<button type="button" class="entry__seg-opt${on ? ' is-on' : ''}" role="radio" aria-checked="${on}" ${attr}>${label}</button>`;
    el.monthOpts.innerHTML = near.map((m) => opt(ym(m) === s.month, `data-month="${ym(m)}"`, monthLabel(m))).join('')
      + opt(otherMonth, 'data-open="month"', otherMonth ? monthLabel(parseDay(`${s.month}-01`)) : 'Other');
    el.monthOpts.querySelectorAll('[data-month]').forEach((b) => b.addEventListener('click', () => {
      s.month = b.dataset.month;
      s.monthPicked = s.month !== ym(s.date);
      renderReview();
    }));
    el.monthOpts.querySelector('[data-open]').addEventListener('click', () => go('month'));
    el.noteValue.textContent = s.note.trim() || 'Add a note';
    el.noteValue.classList.toggle('is-set', !!s.note.trim());
    el.repeatField.hidden = !!s.id;
    root.querySelectorAll('[data-repeat]').forEach((b) => radio(b, b.dataset.repeat === s.repeat));
    el.rule.hidden = !s.recurring;
    if (s.recurring) { el.ruleLink.textContent = s.recurringTitle || 'entry'; el.ruleLink.href = `${root.dataset.rules}${s.recurring}/`; }
    el.del.hidden = !s.id;
    el.save.textContent = s.id ? 'Save changes' : `Add ${income ? 'income' : 'expense'}`;
  }
  function renderCalendar() {
    const first = calView;
    el.calTitle.textContent = `${monthName(first, true)} ${first.getFullYear()}`;
    const start = new Date(first); start.setDate(1 - first.getDay());
    const days = ['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d) => `<span class="entry__cal-dow">${d}</span>`);
    for (let i = 0; i < 42; i++) {
      const d = new Date(start); d.setDate(start.getDate() + i);
      if (i >= 35 && d.getMonth() !== first.getMonth()) break;
      const cls = ['entry__day', d.getMonth() !== first.getMonth() ? 'is-out' : '', iso(d) === iso(s.date) ? 'is-on' : '', iso(d) === iso(today) ? 'is-today' : ''].join(' ');
      days.push(`<button type="button" class="${cls}" data-pick="${iso(d)}">${d.getDate()}</button>`);
    }
    el.cal.innerHTML = days.join('');
    el.cal.querySelectorAll('[data-pick]').forEach((b) => b.addEventListener('click', () => pickDate(parseDay(b.dataset.pick))));
  }
  function pickDate(d) {
    s.date = d;
    if (!s.monthPicked) s.month = ym(d);
    if (page === 'review') renderReview();
    else go('review', { back: true });
  }
  root.querySelectorAll('[data-day-ago]').forEach((b) => b.addEventListener('click', () => {
    const d = new Date(today); d.setDate(d.getDate() - Number(b.dataset.dayAgo));
    pickDate(d);
  }));
  root.querySelectorAll('[data-cal]').forEach((b) => b.addEventListener('click', () => { calView = addMonths(calView, Number(b.dataset.cal)); renderCalendar(); }));
  function renderMonths() {
    const own = new Date(s.date.getFullYear(), s.date.getMonth(), 1);
    const out = [];
    for (let n = -3; n <= 2; n++) {
      const m = addMonths(own, n);
      const v = ym(m);
      out.push(`<button type="button" class="entry__choice${v === s.month ? ' is-on' : ''}" data-month="${v}">${monthName(m, true)} ${m.getFullYear()}${n === 0 ? '<span class="entry__choice-sub">Month of the date</span>' : ''}</button>`);
    }
    el.months.innerHTML = out.join('');
    el.months.querySelectorAll('[data-month]').forEach((b) => b.addEventListener('click', () => {
      s.month = b.dataset.month;
      s.monthPicked = s.month !== ym(s.date);
      go('review', { back: true });
    }));
  }
  root.querySelectorAll('[data-repeat]').forEach((b) => b.addEventListener('click', () => { s.repeat = b.dataset.repeat; renderReview(); }));
  root.querySelector('[data-done]').addEventListener('click', () => { s.note = el.note.value; go('review', { back: true }); });
  root.querySelectorAll('[data-open]').forEach((b) => b.addEventListener('click', () => go(b.dataset.open)));
  root.querySelectorAll('[data-goto]').forEach((b) => b.addEventListener('click', () => go(b.dataset.goto)));

  // ---------- summary chips (what's been entered so far; tap to change)
  function renderSummary() {
    if (!s || page === 'review' || !MAIN.includes(page)) { el.summary.innerHTML = ''; el.summary.hidden = true; return; }
    const chips = [];
    if (page !== 'amount' && amountValue() > 0) chips.push(['amount', `${s.type === 'income' ? '+' : '−'}${money(amountValue())}`]);
    if (!['amount', 'title'].includes(page) && s.title) chips.push(['title', s.title]);
    el.summary.innerHTML = chips.map(([p, t]) => `<button type="button" class="bh-chip" data-chip="${p}">${esc(t)}</button>`).join('');
    el.summary.hidden = !chips.length;
    el.summary.querySelectorAll('[data-chip]').forEach((b) => b.addEventListener('click', () => go(b.dataset.chip)));
  }

  // ---------- navigation
  function show(name) {
    Object.entries(pages).forEach(([k, p]) => { p.hidden = k !== name; });
    page = name;
    const i = MAIN.indexOf(MAIN.includes(name) ? name : 'review');
    el.dots.forEach((d, j) => { d.className = j < i ? 'is-done' : j === i ? 'is-on' : ''; });
    el.dots[0].parentElement.hidden = !!s.id;
    el.back.style.visibility = trail.length ? 'visible' : 'hidden';
    pages[name].classList.remove('is-in'); void pages[name].offsetWidth; pages[name].classList.add('is-in');
    if (name === 'amount') renderAmount();
    if (name === 'title') {
      el.title.value = s.title;
      renderSuggest();
      // Focus inside the tap that got here, so the phone raises its keyboard straight away.
      el.title.focus({ preventScroll: true });
    } else if (document.activeElement === el.title) {
      el.title.blur();
    }
    if (name === 'category') markCategory();
    if (name === 'review') renderReview();
    if (name === 'date') { calView = new Date(s.date.getFullYear(), s.date.getMonth(), 1); renderCalendar(); }
    if (name === 'month') renderMonths();
    if (name === 'note') { el.note.value = s.note; el.note.focus({ preventScroll: true }); }
    else if (document.activeElement === el.note) el.note.blur();
    renderSummary();
    el.error.textContent = '';
  }
  function go(name, { back = false } = {}) {
    if (name === page) return;
    if (back) {
      // Returning from a detail page: drop it from the trail.
      const at = trail.lastIndexOf(name);
      trail = at >= 0 ? trail.slice(0, at) : trail;
    } else {
      if (page === 'title') s.title = el.title.value.trim();
      trail.push(page);
    }
    show(name);
  }
  // Finishing a page reached from the review goes back to the review; otherwise on to ``next``.
  function after(next) {
    if (page === 'title') s.title = el.title.value.trim();
    if (trail.includes('review')) go('review', { back: true });
    else go(next);
  }
  el.back.addEventListener('click', () => { if (trail.length) show(trail.pop()); else close(); });
  root.querySelectorAll('[data-next]').forEach((b) => b.addEventListener('click', () => {
    if (b.dataset.next === 'amount' && amountValue() > 0) after(s.title && s.category ? 'review' : 'title');
    if (b.dataset.next === 'title') titleDone();
  }));

  // Keyboard on desktop: type the amount, Enter moves on, Escape closes.
  root.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { e.preventDefault(); close(); return; }
    if (page !== 'amount' || e.metaKey || e.ctrlKey || e.altKey) return;
    if (/^[0-9]$/.test(e.key) || e.key === '.' || e.key === ',') { e.preventDefault(); key(e.key === ',' ? '.' : e.key); }
    else if (e.key === 'Backspace') { e.preventDefault(); key('back'); }
    else if (e.key === 'Enter') { e.preventDefault(); el.amountNext.click(); }
  });

  // Keep the panel inside the part of the screen the keyboard leaves free.
  const vv = window.visualViewport;
  function fit() {
    if (!vv || root.hidden) return;
    root.style.setProperty('--vvh', `${vv.height}px`);
    root.style.setProperty('--vvt', `${vv.offsetTop}px`);
    root.classList.toggle('is-kb', window.innerHeight - vv.height > 120);
  }
  if (vv) { vv.addEventListener('resize', fit); vv.addEventListener('scroll', fit); }

  // ---------- open / close
  function open(spend, opts = {}) {
    const amount = spend ? String(spend.amount).split('.') : ['', ''];
    s = {
      id: spend ? spend.id : null,
      editing: !!spend,
      type: spend ? spend.type : 'expense',
      int: spend ? amount[0] : '',
      dec: spend && amount[1] && amount[1] !== '00' ? amount[1].replace(/0+$/, '') : '',
      hasDec: !!(spend && amount[1] && amount[1] !== '00'),
      title: spend ? spend.title : '',
      category: spend ? spend.category : (opts.category ? Number(opts.category) : null),
      date: spend ? parseDay(spend.date) : new Date(today),
      month: spend ? spend.month : ym(today),
      monthPicked: spend ? spend.month !== spend.date.slice(0, 7) : false,
      note: spend ? spend.note : '',
      repeat: '',
      recurring: spend ? spend.recurring : null,
      recurringTitle: spend ? spend.recurring_title : '',
    };
    trail = [];
    setType(s.type);
    const day2 = new Date(today); day2.setDate(day2.getDate() - 2);
    root.querySelectorAll('[data-weekday]').forEach((b) => { b.textContent = day2.toLocaleDateString(undefined, { weekday: b.dataset.weekday }); });
    root.hidden = false;
    document.documentElement.classList.add('entry-open');
    fit();
    if (!pushed) { history.pushState({ entry: true }, ''); pushed = true; }
    show(spend ? 'review' : 'amount');
    el.panel.focus({ preventScroll: true });
  }
  function close({ fromPop = false } = {}) {
    if (root.hidden) return;
    if (document.activeElement && root.contains(document.activeElement)) document.activeElement.blur();
    root.hidden = true;
    document.documentElement.classList.remove('entry-open');
    if (pushed && !fromPop) { pushed = false; history.back(); }
    pushed = false;
  }
  window.addEventListener('popstate', () => { if (!root.hidden) close({ fromPop: true }); });
  root.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => close()));

  document.addEventListener('click', (e) => {
    const adder = e.target.closest('[data-add-spend]');
    if (adder) { e.preventDefault(); open(null, { category: adder.dataset.category }); return; }
    const row = e.target.closest('[data-spend]');
    if (row) { e.preventDefault(); open(JSON.parse(row.dataset.spend)); }
  });

  // ---------- save / delete / undo
  function payload(src) {
    return {
      type: src.type, amount: amountValue().toFixed(2), title: src.title, category: src.category,
      date: iso(src.date), month: src.month, note: src.note, repeat: src.repeat,
    };
  }
  el.save.addEventListener('click', async () => {
    if (busy) return;
    if (!s.category) { go('category'); return; }
    busy = true; el.save.disabled = true;
    try {
      const url = s.id ? root.dataset.update.replace('/0/', `/${s.id}/`) : root.dataset.create;
      const res = await post(url, payload(s));
      if (!res.ok) { el.error.textContent = Object.values(res.errors || {}).join(' ') || "Couldn't save."; return; }
      close();
      changed();
      toast(res.toast, { action: res.undo ? { label: 'Undo', run: () => undo(res.undo) } : null });
    } catch (_) {
      el.error.textContent = "Couldn't save. Check your connection and try again.";
    } finally {
      busy = false; el.save.disabled = false;
    }
  });
  async function undo(url) {
    try { await post(url, {}); changed(); toast('Removed', { mood: 'happy' }); }
    catch (_) { toast("Couldn't undo. Delete it from History instead.", { mood: 'worried' }); }
  }
  el.del.addEventListener('click', async () => {
    if (!s.id || busy) return;
    busy = true;
    try {
      const res = await post(root.dataset.delete.replace('/0/', `/${s.id}/`), {});
      close();
      changed();
      const d = res.spend;
      toast(res.toast, {
        mood: 'happy',
        action: { label: 'Undo', run: async () => {
          await post(root.dataset.create, { type: d.type, amount: d.amount, title: d.title, category: d.category, date: d.date, month: d.month, note: d.note });
          changed();
        } },
      });
    } catch (_) {
      el.error.textContent = "Couldn't delete. Check your connection and try again.";
    } finally { busy = false; }
  });

  // PWA shortcut / deep link: /?add=1 opens the flow.
  if (new URLSearchParams(location.search).has('add')) open(null);
}
