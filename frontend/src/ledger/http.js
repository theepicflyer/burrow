// POST a FormData (or plain object) and return the parsed JSON body.
export async function post(url, data) {
  const body = data instanceof FormData ? data : Object.entries(data || {}).reduce((fd, [k, v]) => {
    if (v !== undefined && v !== null) fd.append(k, v);
    return fd;
  }, new FormData());
  const csrf = document.querySelector('meta[name=csrf-token]')?.content || '';
  const res = await fetch(url, {
    method: 'POST',
    body,
    headers: { 'X-CSRFToken': csrf, Accept: 'application/json' },
    credentials: 'same-origin',
  });
  let json = null;
  try { json = await res.json(); } catch (_) { /* not JSON */ }
  if (!json) throw new Error(`HTTP ${res.status}`);
  return json;
}

// The ledger changed: re-render the page body from the current URL (keeps filters).
export function changed() {
  const body = document.getElementById('page-body');
  if (body && window.htmx) {
    window.htmx.ajax('GET', window.location.pathname + window.location.search, {
      target: '#page-body', select: '#page-body', swap: 'outerHTML',
    });
  }
}
