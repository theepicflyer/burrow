// Mobile transaction entry — paged flow.
// State + render is plain JS; the actual form values land in hidden inputs
// inside #tx-mobile-form so the existing Django view processes them unchanged.
(function () {
  const root = document.getElementById('tx-mobile-app');
  if (!root) return;

  // ── Data loaded from the page ────────────────────────────────────────────
  const CATEGORIES = JSON.parse(document.getElementById('tx-mobile-categories').textContent);
  const TAGS = JSON.parse(document.getElementById('tx-mobile-tags').textContent);
  const ENTITIES = JSON.parse(document.getElementById('tx-mobile-entities').textContent);

  // ── Helpers ──────────────────────────────────────────────────────────────
  const $form = document.getElementById('tx-mobile-form');
  const formInput = (name) => $form.querySelector(`input[name="${name}"]`);
  const stableHue = (str) => {
    let h = 0;
    for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) & 0xffffffff;
    return Math.abs(h) % 360;
  };
  const initialOf = (name) => {
    const t = (name || '').trim();
    if (!t) return '?';
    return t[0].toUpperCase();
  };

  // ── Icons (inline SVGs) ──────────────────────────────────────────────────
  const Icon = {
    back:    `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 5l-7 7 7 7"/></svg>`,
    chev:    `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>`,
    chevSm:  `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>`,
    check:   `<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l4.5 4.5L19 7"/></svg>`,
    checkSm: `<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l4.5 4.5L19 7"/></svg>`,
    checkXs: `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l4.5 4.5L19 7"/></svg>`,
    arrowUp: `<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5m0 0l-6 6m6-6l6 6"/></svg>`,
    arrowDn: `<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14m0 0l-6-6m6 6l6-6"/></svg>`,
    clock:   `<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l2.5 2"/></svg>`,
    clockSm: `<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l2.5 2"/></svg>`,
    cal:     `<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"><rect x="4" y="5.5" width="16" height="14" rx="2.5"/><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4"/></svg>`,
    ref:     `<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M4 8.5c0-1.1.9-2 2-2h12a2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2v-11z"/><path d="M4 12h16"/><path d="M8 4.5v3M16 4.5v3" stroke-linecap="round"/><circle cx="12" cy="16.5" r="1.25" fill="currentColor"/></svg>`,
    tag:     `<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round"><path d="M3.5 12.5l9-9H20v7.5l-9 9-7.5-7.5z"/><circle cx="15.5" cy="8.5" r="1.25" fill="currentColor"/></svg>`,
    people:  `<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"><circle cx="9" cy="9" r="3.25"/><path d="M3.5 19c.7-2.9 2.9-4.5 5.5-4.5s4.8 1.6 5.5 4.5"/><path d="M16 5.5a3 3 0 010 6m4.5 7.5c-.4-1.7-1.4-3-2.8-3.7"/></svg>`,
    cat:     `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.75"><rect x="3.5" y="3.5" width="7" height="7" rx="1.75"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.75"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.75"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.75"/></svg>`,
    coins:   `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><ellipse cx="12" cy="6.5" rx="7.5" ry="3.5"/><path d="M4.5 6.5v6c0 1.9 3.4 3.5 7.5 3.5s7.5-1.6 7.5-3.5v-6"/><path d="M4.5 12.5v5c0 1.9 3.4 3.5 7.5 3.5s7.5-1.6 7.5-3.5v-5"/></svg>`,
    note:    `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 5h14M5 10h14M5 15h9"/></svg>`,
    bs:      `<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round"><path d="M20 6H9.5a2 2 0 00-1.5.7L3 12l5 5.3a2 2 0 001.5.7H20a1 1 0 001-1V7a1 1 0 00-1-1z"/><path stroke-linecap="round" d="M12 9.5l5 5M17 9.5l-5 5"/></svg>`,
    x:       `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>`,
    xs:      `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>`,
    lockSm:  `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M7 11V8a5 5 0 0110 0v3"/><rect x="5" y="11" width="14" height="9" rx="2"/></svg>`,
  };

  // ── State ────────────────────────────────────────────────────────────────
  const STEPS = ['amount', 'title', 'typestatus', 'category', 'date', 'review'];
  const defaultDate = root.dataset.defaultDate;            // ISO YYYY-MM-DD
  const defaultType = root.dataset.defaultType || 'EX';    // IN / EX

  const state = {
    step: 0,
    direction: 'forward',
    maxReached: 0,
    saved: false,

    // Form values
    intDigits: '',
    decDigits: '',
    hasDecimal: false,
    desc: '',
    type: defaultType === 'IN' ? 'income' : 'expense',
    typeUserSet: false,
    statusV: 'paid',
    statusUserSet: false,
    category: null, // category id
    date: null,     // Date

    // Optional (review)
    refMonth: null, // Date or null (null = derive from date)
    tags: [],
    entities: [],
    notes: '',

    // Sheets
    sheet: null,
    // Draft state for sheets that need Done
    amountSheet: { i: '', d: '', dec: false },
    titleDraft: '',
    tsDraft: { type: null, status: null },
  };

  // Pre-populate date from server default
  if (defaultDate) {
    const [Y, M, D] = defaultDate.split('-').map(n => parseInt(n, 10));
    state.date = new Date(Y, M - 1, D);
  }

  const tsTimer = { id: null };

  // ── Computed helpers ─────────────────────────────────────────────────────
  function getCents() {
    const i = (state.intDigits.replace(/^0+(?=\d)/, '') || '0');
    const d = (state.decDigits + '00').slice(0, 2);
    const n = parseInt(i, 10) * 100 + parseInt(d, 10);
    return isNaN(n) ? 0 : n;
  }
  function fmtAmount(cents) {
    return (cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  // Mirrors what the user has actually typed: integer-only until '.' is pressed,
  // then "12,345." → "12,345.5" → "12,345.50" as decimal digits stream in.
  function fmtTypedAmount(intDigits, decDigits, hasDecimal) {
    const cleaned = (intDigits.replace(/^0+(?=\d)/, '') || '0');
    const intStr = (parseInt(cleaned, 10) || 0).toLocaleString('en-US');
    return hasDecimal ? intStr + '.' + decDigits : intStr;
  }
  function fmtDate(d) {
    if (!d) return '';
    const now = new Date(); now.setHours(0,0,0,0);
    const dd = new Date(d); dd.setHours(0,0,0,0);
    const diff = Math.round((dd - now) / 86400000);
    if (diff === 0) return 'Today';
    if (diff === -1) return 'Yesterday';
    if (diff === 1) return 'Tomorrow';
    return dd.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
  }
  function fmtMonth(d) { return d ? new Date(d).toLocaleDateString(undefined, { month: 'short', year: 'numeric' }) : ''; }
  function fmtMonthLong(d) { return d ? new Date(d).toLocaleDateString(undefined, { month: 'long', year: 'numeric' }) : ''; }
  function effectiveRefMonth() {
    if (state.refMonth) return state.refMonth;
    if (state.date) return new Date(state.date.getFullYear(), state.date.getMonth(), 1);
    return null;
  }
  function accentVar() {
    return state.type === 'income' ? 'var(--color-success)' : 'var(--color-error)';
  }
  function accentContent() {
    return state.type === 'income' ? 'var(--color-success-content)' : 'var(--color-error-content)';
  }
  function categoryById(id) { return CATEGORIES.find(c => c.id === id); }

  // ── Navigation ───────────────────────────────────────────────────────────
  function goNext() {
    state.direction = 'forward';
    state.step = Math.min(state.step + 1, STEPS.length - 1);
    state.maxReached = Math.max(state.maxReached, state.step);
    render();
  }
  function goBack() {
    state.direction = 'back';
    state.step = Math.max(0, state.step - 1);
    render();
  }
  function goTo(i) {
    if (i > state.maxReached) return;
    state.direction = i > state.step ? 'forward' : 'back';
    state.step = i;
    render();
  }
  function autoAdvance(delay) {
    setTimeout(goNext, delay || 240);
  }

  // ── Numpad input ─────────────────────────────────────────────────────────
  function onNumKey(k) {
    if (k === 'back') {
      if (state.decDigits.length > 0) state.decDigits = state.decDigits.slice(0, -1);
      else if (state.hasDecimal) state.hasDecimal = false;
      else if (state.intDigits.length > 0) state.intDigits = state.intDigits.slice(0, -1);
    } else if (k === '.') {
      if (!state.hasDecimal) {
        state.hasDecimal = true;
        if (state.intDigits === '') state.intDigits = '0';
      }
    } else if (state.hasDecimal) {
      if (state.decDigits.length < 2) state.decDigits += k;
    } else {
      if ((state.intDigits + k).length <= 9) state.intDigits = state.intDigits === '0' ? k : state.intDigits + k;
    }
    if (navigator.vibrate) try { navigator.vibrate(6); } catch (e) {}
    render();
  }

  // Same logic, but mutating the sheet draft instead of step-1 state
  function onAmountSheetKey(k) {
    const s = state.amountSheet;
    if (k === 'back') {
      if (s.d.length > 0) s.d = s.d.slice(0, -1);
      else if (s.dec) s.dec = false;
      else if (s.i.length > 0) s.i = s.i.slice(0, -1);
    } else if (k === '.') {
      if (!s.dec) { s.dec = true; if (s.i === '') s.i = '0'; }
    } else if (s.dec) {
      if (s.d.length < 2) s.d += k;
    } else {
      if ((s.i + k).length <= 9) s.i = s.i === '0' ? k : s.i + k;
    }
    if (navigator.vibrate) try { navigator.vibrate(6); } catch (e) {}
    render();
  }

  // ── Render ───────────────────────────────────────────────────────────────
  function attr(o) {
    return Object.entries(o).map(([k, v]) => v == null || v === false ? '' : `${k}="${String(v).replace(/"/g, '&quot;')}"`).join(' ');
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function summaryItems() {
    const items = [];
    const cents = getCents();
    if (cents > 0) {
      items.push({ step: 0, key: 'amount', text: '$' + fmtAmount(cents), bold: true, color: accentVar(), icon: Icon.coins });
    }
    if (state.desc.trim()) items.push({ step: 1, key: 'desc', text: state.desc, icon: Icon.note });
    if (state.typeUserSet && state.type) {
      items.push({ step: 2, key: 'type', text: state.type === 'income' ? 'Income' : 'Expense', color: accentVar(),
                   icon: state.type === 'income' ? Icon.arrowDn : Icon.arrowUp });
    }
    if (state.statusUserSet && state.statusV) {
      items.push({ step: 2, key: 'status', text: state.statusV === 'paid' ? 'Paid' : 'Projected',
                   icon: state.statusV === 'paid' ? Icon.check : Icon.clock });
    }
    if (state.category) {
      const c = categoryById(state.category);
      if (c) {
        const hue = stableHue(c.name);
        items.push({ step: 3, key: 'category', text: c.name, color: `oklch(0.72 0.12 ${hue})`, icon: Icon.cat });
      }
    }
    if (state.date && state.step > 4) items.push({ step: 4, key: 'date', text: fmtDate(state.date), icon: Icon.cal });
    return items;
  }

  function canProceed() {
    switch (STEPS[state.step]) {
      case 'amount': return getCents() > 0;
      case 'title': return state.desc.trim().length > 0;
      case 'typestatus': return !!state.type && !!state.statusV && state.typeUserSet && state.statusUserSet;
      case 'category': return !!state.category;
      case 'date': return !!state.date;
      case 'review': return true;
      default: return false;
    }
  }
  function promptForStep(s) {
    return {
      amount: 'Enter an amount',
      title: 'Give it a title',
      typestatus: 'Pick one from each',
      category: 'Pick a category',
      date: 'Pick a date',
      review: 'Review',
    }[s] || 'Continue';
  }

  // Tracks the step shown by the previous render so the page-slide animation
  // only plays on step changes, not on every intra-step re-render (e.g. keypad).
  let renderedStep = -1;
  // Tracks the sheet shown by the previous render so the bottom-sheet slides up
  // only when freshly opened, not on every re-render while it stays open.
  let renderedSheet = null;
  // Chip keys present in the previous render — new keys appear with txChipPop.
  let renderedChipKeys = new Set();

  function render() {
    // Set the per-render accent on the root so all child elements can pick it up
    root.style.setProperty('--bc-accent', accentVar());
    root.style.setProperty('--bc-accent-content', state.type === 'income' ? 'var(--color-success-content)' : 'var(--color-error-content)');

    const stepKey = STEPS[state.step];
    const proceed = canProceed();
    const stepChanged = state.step !== renderedStep;
    renderedStep = state.step;

    // ── Header ──
    const dots = STEPS.map((_, i) => {
      const cls = i < state.step ? 'done' : i === state.step ? 'current' : '';
      return `<span class="tx-dot ${cls}"></span>`;
    }).join('');

    // ── Summary chips ──
    const summary = summaryItems();
    const currentChipKeys = new Set(summary.map(s => s.key));
    const chips = summary.map(s => {
      const ja = !renderedChipKeys.has(s.key) ? 'just-added' : '';
      const icon = s.icon ? `<span class="tx-chip-icon"${s.color ? ` style="color:${s.color}"` : ''}>${s.icon}</span>` : '';
      return `<button type="button" class="tx-chip ${s.bold ? 'bold' : ''} ${ja}" data-goto="${s.step}">${icon}<span class="tx-chip-label">${esc(s.text)}</span></button>`;
    }).join('');
    renderedChipKeys = currentChipKeys;

    // ── Step bodies ──
    let body = '';
    if (stepKey === 'amount') body = renderAmountStep();
    else if (stepKey === 'title') body = renderTitleStep();
    else if (stepKey === 'typestatus') body = renderTypeStatusStep();
    else if (stepKey === 'category') body = renderCategoryStep();
    else if (stepKey === 'date') body = renderDateStep();
    else if (stepKey === 'review') body = renderReviewStep();

    // ── Action bar ──
    let action = '';
    if (stepKey === 'review') {
      action = `<button type="button" class="tx-primary" data-save>${Icon.check} Save transaction</button>`;
    } else {
      const label = proceed ? 'Continue' : promptForStep(stepKey);
      action = `<button type="button" class="tx-primary" ${proceed ? '' : 'disabled'} data-next>${esc(label)}${proceed ? Icon.chev : ''}</button>`;
    }

    // ── Sheets ──
    // A freshly-opened sheet renders closed so the CSS transition can slide it
    // up; while it stays open across re-renders it renders already-open (no
    // re-animation). bindEvents() adds the open class on the next frame.
    const sheetOpen = state.sheet != null;
    const sheetJustOpened = sheetOpen && renderedSheet == null;
    renderedSheet = state.sheet;
    const sheet = renderSheet(sheetOpen && !sheetJustOpened);

    // ── Saved overlay ──
    const saved = state.saved ? `
      <div class="tx-saved">
        <div class="tx-saved-inner">
          <div class="tx-saved-check">${Icon.check}</div>
          <div class="tx-saved-title">Saved</div>
          <div class="tx-saved-sub">Logged to ${esc(effectiveRefMonth() ? fmtMonth(effectiveRefMonth()) : 'your books')}</div>
        </div>
      </div>` : '';

    root.innerHTML = `
      ${saved}
      <div class="tx-header">
        <button type="button" class="tx-iconbtn" ${state.step === 0 ? 'disabled' : ''} data-back>${Icon.back}</button>
        <span class="tx-dots">${dots}</span>
        <a href="/" class="tx-close">Close</a>
      </div>
      ${stepKey === 'review' ? '' : `<div class="tx-summary">${chips}</div>`}
      <div class="tx-pages">
        <div class="tx-page ${stepChanged ? 'anim' : ''} ${state.direction === 'back' ? 'back' : ''}" data-step="${state.step}">
          ${body}
        </div>
      </div>
      <div class="tx-actionbar">${action}</div>
      ${sheet}
    `;

    bindEvents();

    // Slide a freshly-opened sheet up: it rendered closed, flip to open next frame.
    if (sheetJustOpened) {
      requestAnimationFrame(() => {
        root.querySelector('.tx-backdrop')?.classList.add('open');
        root.querySelector('.tx-sheet')?.classList.add('open');
      });
    }

  }

  function renderAmountStep() {
    const cents = getCents();
    return `
      <div class="tx-step-header">
        <div class="tx-step-q">How much?</div>
      </div>
      <div class="tx-step-body">
        <div class="tx-amount-display">
          <div class="tx-amount-number ${cents === 0 ? 'empty' : ''}">
            <span class="tx-amount-currency">$</span><span>${fmtTypedAmount(state.intDigits, state.decDigits, state.hasDecimal)}</span>
          </div>
        </div>
        ${renderNumpad('num')}
      </div>
    `;
  }

  function renderNumpad(kind) {
    const keys = ['1','2','3','4','5','6','7','8','9','.','0','back'];
    const cells = keys.map(k => `
      <button type="button" class="tx-numkey ${k === 'back' ? 'flat' : ''}" data-key="${k}" data-numpad="${kind}">
        ${k === 'back' ? Icon.bs : k}
      </button>
    `).join('');
    return `<div class="tx-numpad">${cells}</div>`;
  }

  function renderTitleStep() {
    return `
      <div class="tx-step-header">
        <div class="tx-step-q">What do you call it?</div>
        <div class="tx-step-h">A short title to recognize it later</div>
      </div>
      <div class="tx-step-body">
        <div style="padding:6px 4px;">
          <input id="tx-title-input" class="tx-text-input" placeholder="Whole Foods, gym, paycheck..." value="${esc(state.desc)}" autocomplete="off">
          <div class="tx-text-hint">Return to continue</div>
        </div>
      </div>
    `;
  }

  function bigChoice(o) {
    const content = o.contentColor || 'var(--color-base-100)';
    return `
      <button type="button" class="tx-bigchoice ${o.selected ? 'selected' : ''} ${o.dashed ? 'dashed' : ''}"
              style="--bc-accent:${o.accent};--bc-accent-content:${content};" data-bc="${o.action}">
        <span class="tx-bigchoice-icon">${o.icon}</span>
        <span style="flex:1;min-width:0;">
          <span class="tx-bigchoice-label" style="display:block">${esc(o.label)}</span>
          <span class="tx-bigchoice-sub">${esc(o.sub)}</span>
        </span>
        <span class="tx-bigchoice-radio">${o.selected ? Icon.checkXs : ''}</span>
      </button>
    `;
  }

  function renderTypeStatusStep() {
    return `
      <div class="tx-step-header">
        <div class="tx-step-q">What kind of transaction?</div>
        <div class="tx-step-h">Pick one from each row</div>
      </div>
      <div class="tx-step-body">
        <div style="margin-bottom:18px;">
          <div class="tx-group-label">Direction</div>
          <div style="display:flex;flex-direction:column;gap:8px;">
            ${bigChoice({icon:Icon.arrowUp, label:'Expense', sub:'Money out', accent:'var(--color-error)', contentColor:'var(--color-error-content)', selected: state.typeUserSet && state.type === 'expense', action:'type-expense'})}
            ${bigChoice({icon:Icon.arrowDn, label:'Income', sub:'Money in', accent:'var(--color-success)', contentColor:'var(--color-success-content)', selected: state.typeUserSet && state.type === 'income', action:'type-income'})}
          </div>
        </div>
        <div>
          <div class="tx-group-label">Status</div>
          <div style="display:flex;flex-direction:column;gap:8px;">
            ${bigChoice({icon:Icon.check, label:'Paid', sub:"It's done", accent:'var(--color-base-content)', contentColor:'var(--root-bg)', selected: state.statusUserSet && state.statusV === 'paid', action:'status-paid'})}
            ${bigChoice({icon:Icon.clock, label:'Projected', sub:'Will happen', accent:'color-mix(in oklch, var(--color-base-content) 60%, transparent)', contentColor:'var(--root-bg)', selected: state.statusUserSet && state.statusV === 'projected', dashed:true, action:'status-projected'})}
          </div>
        </div>
      </div>
    `;
  }

  function renderCategoryStep() {
    const grid = CATEGORIES.map(c => {
      const on = state.category === c.id;
      const hue = stableHue(c.name);
      return `
        <button type="button" class="tx-cat-tile ${on ? 'selected' : ''}" style="--cat-hue:${hue};" data-cat="${c.id}">
          <span class="tx-cat-swatch"></span>
          <span class="tx-cat-label">${esc(c.name)}</span>
        </button>
      `;
    }).join('');
    const empty = CATEGORIES.length === 0
      ? `<div style="text-align:center;color:color-mix(in oklch, var(--color-base-content) 55%, transparent);padding:24px 8px;font-size:14px;">No active categories yet. <a href="/categories/" style="color:var(--color-primary);">Add one</a> first.</div>`
      : '';
    return `
      <div class="tx-step-header">
        <div class="tx-step-q">What was it for?</div>
      </div>
      <div class="tx-step-body">
        ${empty}
        <div class="tx-cat-grid">${grid}</div>
      </div>
    `;
  }

  function renderCalendar(value, target) {
    const v = value ? new Date(value) : new Date();
    const view = window['_tx_view_' + target] || new Date(v.getFullYear(), v.getMonth(), 1);
    window['_tx_view_' + target] = view;
    const year = view.getFullYear();
    const month = view.getMonth();
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const today = new Date(); today.setHours(0,0,0,0);
    const selKey = value ? new Date(value).toDateString() : null;
    const monthName = view.toLocaleString('default', { month: 'long', year: 'numeric' });
    let cells = '';
    for (let i = 0; i < firstDay; i++) cells += '<div></div>';
    for (let d = 1; d <= daysInMonth; d++) {
      const dt = new Date(year, month, d);
      const isSel = dt.toDateString() === selKey;
      const isToday = dt.getTime() === today.getTime();
      cells += `<button type="button" class="tx-cal-cell ${isSel ? 'selected' : ''}" data-day="${dt.toISOString()}" data-calendar-target="${target}">${d}${isToday && !isSel ? '<span class="tx-today-dot"></span>' : ''}</button>`;
    }
    return `
      <div class="tx-calendar-card">
        <div class="tx-cal-head">
          <button type="button" class="tx-cal-nav" data-cal-nav="prev" data-cal-target="${target}">${Icon.back}</button>
          <div class="tx-cal-month">${esc(monthName)}</div>
          <button type="button" class="tx-cal-nav" data-cal-nav="next" data-cal-target="${target}">${Icon.chev}</button>
        </div>
        <div class="tx-cal-dow">${['S','M','T','W','T','F','S'].map(d => `<div>${d}</div>`).join('')}</div>
        <div class="tx-cal-grid">${cells}</div>
      </div>
    `;
  }

  function renderShortcuts(value, target) {
    const shortcuts = [
      { label: 'Today', d: new Date() },
      { label: 'Yesterday', d: new Date(Date.now() - 86400000) },
      { label: '2 days ago', d: new Date(Date.now() - 2*86400000) },
      { label: '3 days ago', d: new Date(Date.now() - 3*86400000) },
      { label: 'Last week', d: new Date(Date.now() - 7*86400000) },
      { label: '2 weeks ago', d: new Date(Date.now() - 14*86400000) },
    ];
    return `
      <div class="tx-shortcuts-divider">
        <div class="tx-group-label">Shortcuts</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;">
          ${shortcuts.map(s => {
            const dCheck = new Date(s.d); dCheck.setHours(0,0,0,0);
            const isSel = value && new Date(value).setHours(0,0,0,0) === dCheck.getTime();
            return `<button type="button" class="tx-shortcut ${isSel ? 'selected' : ''}" data-shortcut="${dCheck.toISOString()}" data-shortcut-target="${target}">${esc(s.label)}</button>`;
          }).join('')}
        </div>
      </div>
    `;
  }

  function renderDateStep() {
    return `
      <div class="tx-step-header">
        <div class="tx-step-q">When?</div>
        <div class="tx-step-h">Pick a day or use a shortcut</div>
      </div>
      <div class="tx-step-body">
        ${renderCalendar(state.date, 'step')}
        ${renderShortcuts(state.date, 'step')}
      </div>
    `;
  }

  function renderReviewStep() {
    const cat = state.category ? categoryById(state.category) : null;
    const hue = cat ? stableHue(cat.name) : 60;
    const sign = state.type === 'expense' ? '−' : '+';

    const tagsPreview = state.tags.length
      ? state.tags.slice(0, 3).join(', ') + (state.tags.length > 3 ? ` +${state.tags.length - 3}` : '')
      : 'None';
    const peoplePreview = state.entities.length
      ? state.entities.slice(0, 2).join(', ') + (state.entities.length > 2 ? ` +${state.entities.length - 2}` : '')
      : 'None';
    const peopleAvatars = state.entities.length
      ? `<div class="tx-people-avatars">${state.entities.slice(0, 3).map(name => {
          const h = stableHue(name);
          return `<div class="av" style="background:oklch(0.55 0.12 ${h});">${esc(initialOf(name))}</div>`;
        }).join('')}</div>`
      : '';

    return `
      <div class="tx-step-header">
        <div class="tx-step-q">All set?</div>
        <div class="tx-step-h">Tap anything to edit. Add what you want, then save.</div>
      </div>
      <div class="tx-step-body">

        <div class="tx-hero">
          <div class="tx-hero-amount" style="color:${accentVar()}" data-open-sheet="amount">
            <span>${sign}</span><span class="sub">$</span><span>${fmtAmount(getCents())}</span>
          </div>
          <div class="tx-hero-title" data-open-sheet="title">${esc(state.desc)}</div>
          <div class="tx-hero-meta">
            <button type="button" class="tx-meta-pill" data-open-sheet="typestatus">
              <span class="dot" style="background:${accentVar()}"></span>${state.type === 'income' ? 'Income' : 'Expense'}
            </button>
            <button type="button" class="tx-meta-pill ${state.statusV === 'projected' ? 'dashed' : ''}" data-open-sheet="typestatus">
              ${state.statusV === 'paid' ? Icon.checkSm : Icon.clockSm} ${state.statusV === 'paid' ? 'Paid' : 'Projected'}
            </button>
            ${state.date ? `<button type="button" class="tx-meta-pill" data-open-sheet="date">${Icon.cal} ${esc(fmtDate(state.date))}</button>` : ''}
          </div>
        </div>

        <button type="button" class="tx-category-card ${cat ? 'has-cat' : ''}" style="--cat-hue:${hue};" data-open-sheet="category">
          <span class="tx-cat-card-swatch">${!cat ? Icon.cat : ''}</span>
          <span style="flex:1;min-width:0;">
            <span class="tx-cat-card-label" style="display:block">Category</span>
            <span class="tx-cat-card-name ${cat ? '' : 'empty'}" style="display:block">${cat ? esc(cat.name) : 'Pick a category'}</span>
          </span>
          ${Icon.chev}
        </button>

        <div class="tx-section-label">Optional</div>

        <button type="button" class="tx-option-row" data-open-sheet="refmonth">
          <span class="icon">${Icon.ref}</span>
          <span class="tx-stack">
            <span class="label" style="display:block">Reference month</span>
            <span class="value ${state.refMonth ? 'set' : 'muted'}" style="display:block">${state.refMonth ? esc(fmtMonthLong(state.refMonth)) : 'Same as date (' + (effectiveRefMonth() ? fmtMonth(effectiveRefMonth()) : '—') + ')'}</span>
          </span>
          ${Icon.chevSm}
        </button>

        <button type="button" class="tx-option-row" data-open-sheet="tags">
          <span class="icon">${Icon.tag}</span>
          <span class="tx-stack">
            <span class="label" style="display:block">Tags</span>
            <span class="value ${state.tags.length ? 'set' : 'muted'}" style="display:block">${esc(tagsPreview)}</span>
          </span>
          ${Icon.chevSm}
        </button>

        <button type="button" class="tx-option-row" data-open-sheet="people">
          <span class="icon">${Icon.people}</span>
          <span class="tx-stack">
            <span class="label" style="display:block">People</span>
            <span class="value ${state.entities.length ? 'set' : 'muted'}" style="display:block">${esc(peoplePreview)}</span>
          </span>
          ${peopleAvatars}
          ${Icon.chevSm}
        </button>

        <div class="tx-section-label" style="margin-top:18px;">Notes</div>
        <textarea id="tx-notes-input" class="tx-notes" placeholder="Receipt details, who reimburses you, why this happened...">${esc(state.notes)}</textarea>

        <div style="height:8px;"></div>
      </div>
    `;
  }

  // ── Sheets ───────────────────────────────────────────────────────────────
  // emitOpen: render the sheet already carrying the `open` class. False when the
  // sheet was just opened — render() then adds `open` on the next frame so the
  // slide-up transition runs.
  function renderSheet(emitOpen) {
    const s = state.sheet;
    let title = '', sub = '', body = '';
    if (s === 'amount') {
      title = 'Edit amount';
      const c = (() => {
        const i = (state.amountSheet.i.replace(/^0+(?=\d)/, '') || '0');
        const d = (state.amountSheet.d + '00').slice(0, 2);
        return parseInt(i, 10) * 100 + parseInt(d, 10);
      })();
      body = `
        <div style="display:flex;justify-content:center;padding:10px 0 14px;">
          <div class="tx-amount-number ${c === 0 ? 'empty' : ''}" style="font-size:48px;">
            <span class="tx-amount-currency" style="font-size:22px;transform:translateY(-12px);">$</span><span>${fmtTypedAmount(state.amountSheet.i, state.amountSheet.d, state.amountSheet.dec)}</span>
          </div>
        </div>
        ${renderNumpad('sheet')}
        <button type="button" class="tx-sheet-done" ${c === 0 ? 'disabled' : ''} data-sheet-done="amount">Done</button>
      `;
    } else if (s === 'title') {
      title = 'Edit title';
      body = `
        <input id="tx-title-sheet-input" class="tx-text-input" placeholder="Whole Foods, gym, paycheck..." value="${esc(state.titleDraft)}" autocomplete="off">
        <button type="button" class="tx-sheet-done" ${state.titleDraft.trim() ? '' : 'disabled'} data-sheet-done="title">Done</button>
      `;
    } else if (s === 'typestatus') {
      title = 'Type & status';
      const d = state.tsDraft;
      const both = d.type && d.status;
      body = `
        <div class="tx-group-label">Direction</div>
        <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:16px;">
          ${bigChoice({icon:Icon.arrowUp, label:'Expense', sub:'Money out', accent:'var(--color-error)', contentColor:'var(--color-error-content)', selected: d.type === 'expense', action:'ts-type-expense'})}
          ${bigChoice({icon:Icon.arrowDn, label:'Income', sub:'Money in', accent:'var(--color-success)', contentColor:'var(--color-success-content)', selected: d.type === 'income', action:'ts-type-income'})}
        </div>
        <div class="tx-group-label">Status</div>
        <div style="display:flex;flex-direction:column;gap:8px;">
          ${bigChoice({icon:Icon.check, label:'Paid', sub:"It's done", accent:'var(--color-base-content)', contentColor:'var(--root-bg)', selected: d.status === 'paid', action:'ts-status-paid'})}
          ${bigChoice({icon:Icon.clock, label:'Projected', sub:'Will happen', accent:'color-mix(in oklch, var(--color-base-content) 60%, transparent)', contentColor:'var(--root-bg)', selected: d.status === 'projected', dashed:true, action:'ts-status-projected'})}
        </div>
        <button type="button" class="tx-sheet-done" ${both ? '' : 'disabled'}
                style="--bc-accent:${d.type === 'income' ? 'var(--color-success)' : 'var(--color-error)'}"
                data-sheet-done="typestatus">Done</button>
      `;
    } else if (s === 'category') {
      title = 'Category';
      const grid = CATEGORIES.map(c => {
        const on = state.category === c.id;
        const hue = stableHue(c.name);
        return `
          <button type="button" class="tx-cat-tile ${on ? 'selected' : ''}" style="--cat-hue:${hue};" data-sheet-cat="${c.id}">
            <span class="tx-cat-swatch"></span>
            <span class="tx-cat-label">${esc(c.name)}</span>
          </button>
        `;
      }).join('');
      body = `<div class="tx-cat-grid">${grid}</div>`;
    } else if (s === 'date') {
      title = 'Date';
      body = `${renderCalendar(state.date, 'sheet')}${renderShortcuts(state.date, 'sheet')}`;
    } else if (s === 'refmonth') {
      title = 'Reference month';
      sub = 'Which month should this transaction land in?';
      const val = effectiveRefMonth();
      const year = window._tx_refmonth_year || (val ? val.getFullYear() : new Date().getFullYear());
      window._tx_refmonth_year = year;
      const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      const selY = val ? val.getFullYear() : null;
      const selM = val ? val.getMonth() : null;
      const grid = months.map((m, i) => {
        const isSel = (selY === year && selM === i);
        return `<button type="button" class="tx-month-btn ${isSel ? 'selected' : ''}" data-month="${year}-${i}">${m}</button>`;
      }).join('');
      const resetBtn = state.refMonth
        ? `<button type="button" class="tx-month-reset" data-refmonth-reset>${Icon.xs} Reset to date's month</button>`
        : '';
      body = `
        <div style="display:flex;align-items:center;justify-content:space-between;padding:0 4px 14px;">
          <button type="button" class="tx-cal-nav" data-refyear="prev">${Icon.back}</button>
          <div style="font-size:15.5px;font-weight:600;letter-spacing:-0.2px;">${year}</div>
          <button type="button" class="tx-cal-nav" data-refyear="next">${Icon.chev}</button>
        </div>
        <div class="tx-month-grid">${grid}</div>
        ${resetBtn}
      `;
    } else if (s === 'tags') {
      title = 'Tags';
      sub = 'Any apply';
      if (TAGS.length === 0) {
        body = `<div style="text-align:center;color:color-mix(in oklch, var(--color-base-content) 55%, transparent);padding:24px 8px;font-size:14px;">No tags yet.</div>`;
      } else {
        body = `<div style="display:flex;flex-wrap:wrap;gap:8px;">
          ${TAGS.map(t => {
            const on = state.tags.includes(t);
            return `<button type="button" class="tx-tagchip ${on ? 'selected' : ''}" data-tag="${esc(t)}">${on ? Icon.checkXs : ''} ${esc(t)}</button>`;
          }).join('')}
        </div>`;
      }
    } else if (s === 'people') {
      title = 'People';
      sub = "Who's involved?";
      if (ENTITIES.length === 0) {
        body = `<div style="text-align:center;color:color-mix(in oklch, var(--color-base-content) 55%, transparent);padding:24px 8px;font-size:14px;">No entities yet.</div>`;
      } else {
        body = ENTITIES.map(name => {
          const on = state.entities.includes(name);
          const h = stableHue(name);
          return `
            <button type="button" class="tx-person-row ${on ? 'selected' : ''}" data-person="${esc(name)}">
              <span class="tx-person-av" style="background:oklch(0.55 0.12 ${h});">${esc(initialOf(name))}</span>
              <span class="tx-person-name">${esc(name)}</span>
              <span class="tx-person-check">${on ? Icon.checkXs : ''}</span>
            </button>
          `;
        }).join('');
      }
    }

    const head = title ? `
      <div class="tx-sheet-head">
        <div>
          <div class="tx-sheet-title">${esc(title)}</div>
          ${sub ? `<div class="tx-sheet-sub">${esc(sub)}</div>` : ''}
        </div>
        <button type="button" class="tx-sheet-close" data-close-sheet>${Icon.x}</button>
      </div>
    ` : '';

    return `
      <div class="tx-backdrop ${emitOpen ? 'open' : ''}" data-close-sheet></div>
      <div class="tx-sheet ${emitOpen ? 'open' : ''}">
        <div class="tx-sheet-grab"><span></span></div>
        ${head}
        <div class="tx-sheet-body">${body}</div>
      </div>
    `;
  }

  // ── Event wiring (delegate per-render) ───────────────────────────────────
  function bindEvents() {
    root.querySelectorAll('[data-back]').forEach(b => b.addEventListener('click', goBack));
    root.querySelectorAll('[data-next]').forEach(b => b.addEventListener('click', () => { if (canProceed()) goNext(); }));
    root.querySelectorAll('[data-save]').forEach(b => b.addEventListener('click', handleSave));
    root.querySelectorAll('[data-goto]').forEach(b => b.addEventListener('click', () => goTo(parseInt(b.dataset.goto, 10))));

    // Numpad
    root.querySelectorAll('[data-key]').forEach(b => {
      b.addEventListener('click', () => {
        if (b.dataset.numpad === 'sheet') onAmountSheetKey(b.dataset.key);
        else onNumKey(b.dataset.key);
      });
    });

    // Title input
    const titleEl = root.querySelector('#tx-title-input');
    if (titleEl) {
      // Focusing during the page-slide makes the browser scroll the still-
      // off-screen input into view, which reads as a bounce. Wait for the
      // slide to finish before focusing (also lets the soft keyboard slide up
      // after the page has settled, not on top of it).
      const focusInput = () => {
        titleEl.focus();
        titleEl.setSelectionRange(titleEl.value.length, titleEl.value.length);
      };
      setTimeout(focusInput, 360);
      titleEl.addEventListener('input', (e) => {
        state.desc = e.target.value;
        // Update button enabled state without re-rendering input
        const btn = root.querySelector('[data-next]');
        if (btn) {
          if (canProceed()) { btn.removeAttribute('disabled'); btn.textContent = ''; btn.innerHTML = `Continue${Icon.chev}`; }
          else { btn.setAttribute('disabled', ''); btn.textContent = promptForStep('title'); }
        }
      });
      titleEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && state.desc.trim()) { e.preventDefault(); goNext(); }
      });
    }
    const titleSheetEl = root.querySelector('#tx-title-sheet-input');
    if (titleSheetEl) {
      titleSheetEl.focus();
      titleSheetEl.setSelectionRange(titleSheetEl.value.length, titleSheetEl.value.length);
      titleSheetEl.addEventListener('input', (e) => {
        state.titleDraft = e.target.value;
        const done = root.querySelector('[data-sheet-done="title"]');
        if (done) {
          if (state.titleDraft.trim()) done.removeAttribute('disabled');
          else done.setAttribute('disabled', '');
        }
      });
      titleSheetEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && state.titleDraft.trim()) {
          e.preventDefault();
          state.desc = state.titleDraft; state.sheet = null; render();
        }
      });
    }

    // Type/Status (step)
    root.querySelectorAll('[data-bc]').forEach(b => {
      b.addEventListener('click', () => {
        const a = b.dataset.bc;
        if (a === 'type-expense') { state.type = 'expense'; state.typeUserSet = true; }
        else if (a === 'type-income') { state.type = 'income'; state.typeUserSet = true; }
        else if (a === 'status-paid') { state.statusV = 'paid'; state.statusUserSet = true; }
        else if (a === 'status-projected') { state.statusV = 'projected'; state.statusUserSet = true; }
        else if (a === 'ts-type-expense') { state.tsDraft.type = 'expense'; }
        else if (a === 'ts-type-income') { state.tsDraft.type = 'income'; }
        else if (a === 'ts-status-paid') { state.tsDraft.status = 'paid'; }
        else if (a === 'ts-status-projected') { state.tsDraft.status = 'projected'; }
        render();
        // Auto-advance when both type+status set on the typestatus step
        if (STEPS[state.step] === 'typestatus' && state.typeUserSet && state.statusUserSet) {
          clearTimeout(tsTimer.id);
          tsTimer.id = setTimeout(goNext, 380);
        }
      });
    });

    // Category step tile
    root.querySelectorAll('[data-cat]').forEach(b => {
      b.addEventListener('click', () => {
        state.category = parseInt(b.dataset.cat, 10);
        render();
        autoAdvance(220);
      });
    });
    root.querySelectorAll('[data-sheet-cat]').forEach(b => {
      b.addEventListener('click', () => {
        state.category = parseInt(b.dataset.sheetCat, 10);
        state.sheet = null;
        render();
      });
    });

    // Calendar
    root.querySelectorAll('[data-cal-nav]').forEach(b => {
      b.addEventListener('click', () => {
        const target = b.dataset.calTarget;
        const key = '_tx_view_' + target;
        const v = window[key];
        const delta = b.dataset.calNav === 'prev' ? -1 : 1;
        window[key] = new Date(v.getFullYear(), v.getMonth() + delta, 1);
        render();
      });
    });
    root.querySelectorAll('[data-day]').forEach(b => {
      b.addEventListener('click', () => {
        const d = new Date(b.dataset.day); d.setHours(0,0,0,0);
        state.date = d;
        // If refMonth was previously cleared (null), keep it that way; user can still override.
        if (b.dataset.calendarTarget === 'sheet') { state.sheet = null; render(); }
        else { render(); autoAdvance(220); }
      });
    });
    root.querySelectorAll('[data-shortcut]').forEach(b => {
      b.addEventListener('click', () => {
        const d = new Date(b.dataset.shortcut); d.setHours(0,0,0,0);
        state.date = d;
        if (b.dataset.shortcutTarget === 'sheet') { state.sheet = null; render(); }
        else { render(); autoAdvance(220); }
      });
    });

    // Sheets — open / close
    root.querySelectorAll('[data-open-sheet]').forEach(b => {
      b.addEventListener('click', () => {
        const which = b.dataset.openSheet;
        if (which === 'amount') state.amountSheet = { i: state.intDigits, d: state.decDigits, dec: state.hasDecimal };
        if (which === 'title') state.titleDraft = state.desc;
        if (which === 'typestatus') state.tsDraft = { type: state.type, status: state.statusV };
        if (which === 'refmonth') window._tx_refmonth_year = (effectiveRefMonth() || new Date()).getFullYear();
        if (which === 'date') window._tx_view_sheet = new Date((state.date || new Date()).getFullYear(), (state.date || new Date()).getMonth(), 1);
        state.sheet = which;
        render();
      });
    });
    root.querySelectorAll('[data-close-sheet]').forEach(b => {
      b.addEventListener('click', (e) => { e.stopPropagation(); state.sheet = null; render(); });
    });

    // Sheet Done
    root.querySelectorAll('[data-sheet-done]').forEach(b => {
      b.addEventListener('click', () => {
        const which = b.dataset.sheetDone;
        if (which === 'amount') {
          state.intDigits = state.amountSheet.i;
          state.decDigits = state.amountSheet.d;
          state.hasDecimal = state.amountSheet.dec;
        } else if (which === 'title') {
          state.desc = state.titleDraft;
        } else if (which === 'typestatus') {
          if (state.tsDraft.type) { state.type = state.tsDraft.type; state.typeUserSet = true; }
          if (state.tsDraft.status) { state.statusV = state.tsDraft.status; state.statusUserSet = true; }
        }
        state.sheet = null;
        render();
      });
    });

    // Refmonth sheet
    root.querySelectorAll('[data-refyear]').forEach(b => {
      b.addEventListener('click', () => {
        window._tx_refmonth_year += (b.dataset.refyear === 'prev' ? -1 : 1);
        render();
      });
    });
    root.querySelectorAll('[data-month]').forEach(b => {
      b.addEventListener('click', () => {
        const [y, m] = b.dataset.month.split('-').map(n => parseInt(n, 10));
        state.refMonth = new Date(y, m, 1);
        state.sheet = null; render();
      });
    });
    root.querySelectorAll('[data-refmonth-reset]').forEach(b => {
      b.addEventListener('click', () => { state.refMonth = null; state.sheet = null; render(); });
    });

    // Tags / People
    root.querySelectorAll('[data-tag]').forEach(b => {
      b.addEventListener('click', () => {
        const t = b.dataset.tag;
        if (state.tags.includes(t)) state.tags = state.tags.filter(x => x !== t);
        else state.tags = [...state.tags, t];
        render();
      });
    });
    root.querySelectorAll('[data-person]').forEach(b => {
      b.addEventListener('click', () => {
        const p = b.dataset.person;
        if (state.entities.includes(p)) state.entities = state.entities.filter(x => x !== p);
        else state.entities = [...state.entities, p];
        render();
      });
    });

    // Notes (review only)
    const notesEl = root.querySelector('#tx-notes-input');
    if (notesEl) {
      notesEl.addEventListener('input', (e) => { state.notes = e.target.value; });
    }
  }

  // ── Save → populate hidden form + submit ─────────────────────────────────
  function localIso(d) {
    if (!d) return '';
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  function handleSave() {
    const cents = getCents();
    const amount = (cents / 100).toFixed(2);
    const dateIso = state.date ? localIso(state.date) : defaultDate;
    const refIso = effectiveRefMonth() ? localIso(effectiveRefMonth()) : '';

    formInput('type').value = state.type === 'income' ? 'IN' : 'EX';
    formInput('is_paid').value = state.statusV === 'paid' ? 'on' : '';
    formInput('date').value = dateIso;
    formInput('reference_date').value = refIso;
    formInput('amount').value = amount;
    formInput('description').value = state.desc.trim();
    formInput('notes').value = state.notes;
    formInput('category').value = state.category || '';

    // tags / entities — multiple values, by name
    const tagsHost = document.getElementById('tx-mobile-tags-inputs');
    tagsHost.innerHTML = '';
    state.tags.forEach(t => {
      const i = document.createElement('input');
      i.type = 'hidden'; i.name = 'tags'; i.value = t;
      tagsHost.appendChild(i);
    });
    const entHost = document.getElementById('tx-mobile-entities-inputs');
    entHost.innerHTML = '';
    state.entities.forEach(e => {
      const i = document.createElement('input');
      i.type = 'hidden'; i.name = 'entities'; i.value = e;
      entHost.appendChild(i);
    });

    state.saved = true;
    render();
    setTimeout(() => $form.submit(), 650);
  }

  // ── Boot ─────────────────────────────────────────────────────────────────
  render();
})();
