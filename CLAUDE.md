# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Cache is a personal finance tracker, published at `github.com/theepicflyer/cache` (public, AGPL-3.0). It is a **hard fork** of `eitchtee/WYGIWYH`: upstream history is kept up to the fork point, but upstream is not tracked or merged. Internal names still say WYGIWYH (the `app/WYGIWYH/` Django project, `wygiwyh` DB/user, `wygiwyh_*` theme keys); leave them, renaming them buys nothing and breaks existing deployments. User-visible text says Cache, and the README credits WYGIWYH. The app was called Burrow until November 2026; Burrow is now only the design system's name, so `burrow` identifiers (`burrow/` folders, `<c-burrow.*>`, `window.burrow*` chart helpers, the `burrow-theme` storage key) belong to the design system and stay.

The app is now the **ledger** (`app/apps/ledger/`): a shared household list of transactions (expenses and income) with budget categories, sinking funds, income categories, recurring transactions and trends, rebuilt from scratch on its own models and UI. The WYGIWYH apps (accounts, currencies, transactions, budgets, ...) are still installed and reachable under `/legacy/` until the old data has been imported and checked; new work goes in the ledger, not there.

The repo is public. Never commit personal data: real names, emails, hostnames, amounts from a real ledger, DB dumps. Use `example.com` and fictional data in docs, tests and screenshots.

## Dev workflow

Use the local prod-parity stack. Same Dockerfile, runtime layout, and supervisord setup as production, but the image is built from the local source tree so feature branches are exercised end-to-end:

```sh
docker compose -f docker-compose.local.yml up -d --build
# app at http://localhost:${OUTBOUND_PORT}  (default 9005 in this checkout)
docker compose -f docker-compose.local.yml logs -f web
```

After editing Python/templates/JS:

```sh
docker compose -f docker-compose.local.yml up -d --build web
```

Rebuild is the cost of production parity — no auto-reload. If you need a fast inner loop, `docker-compose.dev.yml` runs Django + vite with code mounts and HMR, but it has not been the canonical path for this fork's work.

`docker-compose.prod.yml` is the example compose for self-hosters (pulls `ghcr.io/theepicflyer/cache:latest`, bind-mounts `./postgres_data`); do not run it locally.

### One-off commands inside the container

```sh
docker compose -f docker-compose.local.yml exec web python manage.py migrate
docker compose -f docker-compose.local.yml exec web python manage.py makemigrations
docker compose -f docker-compose.local.yml exec web python manage.py shell
docker compose -f docker-compose.local.yml exec db psql -U wygiwyh -d wygiwyh
```

### Seeding the DB

Fresh stack starts with an empty Postgres. To restore from a SQL dump (e.g. a `doctored_*.sql` exported from the prod copy):

```sh
docker compose -f docker-compose.local.yml up -d db
until docker exec wygiwyh_pg pg_isready -U wygiwyh -d wygiwyh >/dev/null 2>&1; do sleep 1; done
cat doctored_*.sql | docker exec -i wygiwyh_pg psql -U wygiwyh -d wygiwyh
docker compose -f docker-compose.local.yml up -d --build web
```

`wygiwyh_*.sql` and `doctored_*.sql` are gitignored — they live locally only.

### Tests / UI verification

Django's test runner, against Postgres. CI (`.github/workflows/ci.yml`) runs it on every PR and before every image build, together with `makemigrations --check`. Templates need the Vite manifest, so build the frontend first. Locally:

```sh
docker run -d --rm --name cache-test-pg -e POSTGRES_USER=wygiwyh -e POSTGRES_PASSWORD=test -e POSTGRES_DB=wygiwyh -p 127.0.0.1:55432:5432 postgres:15-bookworm
npm ci --prefix frontend && npm run build --prefix frontend
cd app && export SECRET_KEY=test SQL_DATABASE=wygiwyh SQL_USER=wygiwyh SQL_PASSWORD=test SQL_HOST=127.0.0.1 SQL_PORT=55432
uv run python manage.py collectstatic --noinput
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test --parallel auto
```

Add tests next to the app (`app/apps/<app>/tests/`) for new behaviour. For UI changes also exercise the affected pages; `manage.py seed_ledger` gives a fictional ledger to look at. If the Claude-in-Chrome MCP integration is connected (`list_connected_browsers` returns a device), drive verification through it: navigate to the affected URL, screenshot, optionally check console errors. The user must log into the running stack themselves; the session cookie then persists for the rest of the agent loop.

### Python tooling

`uv` only. Never `source venv/bin/activate`. For host-side scripts: `uv run python …`. Lockfile is `uv.lock`; bump deps via `uv add`/`uv lock --upgrade`.

## .env

Single `.env` at repo root, loaded by all compose files. Two gotchas:
- `DJANGO_ALLOWED_HOSTS` is **space-separated**, not comma-separated (`settings.py:36`).
- `.env` is gitignored; `.env.example` is the template. For local work, ensure `localhost 127.0.0.1` are in `DJANGO_ALLOWED_HOSTS`.

## Architecture

Django 5.2 + htmx + django-cotton + Vite for assets. Backed by Postgres 15 and Procrastinate for async jobs (runs in-process via supervisord in the single-container deploy). DRF still serves the legacy `/api/`.

### The ledger (`app/apps/ledger/`)

One shared ledger: every signed-in user sees and edits everything, so ledger models have no `owner`/visibility and views do no per-user filtering (`created_by` only records who entered a transaction). There are no accounts or wallet balances.

- **`Category`**: `kind` is `budget` (planned monthly spending), `fund` (sinking fund) or `income` (pay, interest; no monthly amount). Funds also have `opening_balance` and an optional `target`. An income category takes income only (forms and MCP refuse an expense there). `icon` is blank (automatic: `icons.guess()` picks one from words in the name), `letter`, or a name from the icon library; draw it with `{% category_tile cat %}` (icon, else the acorn for a fund, else the first letter) and use `Category.display_icon` in code.
- **`MonthlyAmount`**: effective-dated monthly budget (or fund top-up): the amount for month M is the latest row with `start_month <= M`, 0 before the first. `Category.set_amount(amount, from_month)` changes it from that month on, so **past months keep their amount and past trends never move**. Preserve this; never rewrite old rows to apply a new amount.
- **`Transaction`**: `type` is `expense` or `income` and `amount` is always positive. Income in a budget or fund category is money back (a refund, or money put into a fund); budget and fund maths use net spend (expenses − income, `services.net_amount()`), and `Book.received()` is its negation for income categories. `date` is when it happened or was billed, `month` (day 1) is the month it counts toward. May's transport bill paid on 10 June has `date=2026-06-10, month=2026-05-01`. All budget and fund maths use `month`, never `date`.
- **`Recurring`**: a `type`, amount and category on a schedule (`every` × week/month/year from `start_date`, optional `end_date`, `month_offset` 0 or −1). `services.generate_due()` creates entries only once they fall due (pages and an hourly task call it), so editing a rule changes every entry still to come and nothing already created. `last_generated` is owned by `generate_due`: `Recurring.save()` skips it unless it is named in `update_fields`. Occurrences are computed from `start_date` each time so the 31st never drifts.
- **Fund balance** at the end of M = `opening_balance` + top-ups from the fund's first `MonthlyAmount` month through M − transactions with `month <= M`. It is computed, never stored or materialized.
- **`services.py`**: `Book` loads all monthly amounts and per-(category, month) totals in two queries; `month_status()` (Home: budgets, funds, income lines, `income`/`out`/`net`), `analysis()` (Trends: months over, averages, `consistently_over`, fund balance series, monthly in/out `flows`; running months are `partial` and excluded from counts, as are months before a category had a budget or spend), `category_history()`, `categories_for_entry()` (chips by recent use), `title_suggestions()`, `generate_due()`, `upcoming()`.
- Budgets and funds answer different questions (did spend stay under budget vs what's saved); keep them visually and semantically apart. Home's ring and "left" are budgets only.
- Amounts are one currency, always shown with a plain `$` (`$1,234.50`); there is no currency setting or conversion.
- **`mcp.py`**: the MCP toolset (see `docs/MCP.md`); each tool checks scope itself.
- **`importer.py`** + `manage.py import_wygiwyh [--dry-run] [--replace]`: one-off import of the WYGIWYH tables into the ledger (auto-allocations become `MonthlyAmount` top-ups; per-month budgets become effective-dated rows; the report compares fund balances with the old ones). `manage.py seed_ledger` fills an empty ledger with fictional data for local work and screenshots.

### Pages and URLs

`apps/ledger/urls.py` (namespace `ledger`) is mounted at `/`: Home (`/`: month ring, budget meters, in and out, fund stashes, coming up, latest), History (`/history/`: search, type/month/category filters, paged by day), Trends (`/trends/`), category detail (`/categories/<id>/`), Settings (`/settings/`: categories, the all-amounts editor at `/settings/budgets/`, recurring at `/recurring/`, currency, theme, API tokens for MCP), login/logout. Navigation is the bottom nav on phones and the side rail from 1024px (`templates/ledger/partials/`).

The add/edit flow (`partials/entry.html` + `frontend/src/ledger/entry.js`) is on every page. It is one page at a time so nothing hides behind the phone keyboard: amount on its own numpad (with the expense/income switch; no keyboard), title (keyboard; Return moves on, and tapping a past title fills its category and skips to the review), category grid (a tap moves on), review (amount, title and category in one card; date, counts-toward month and repeat are segmented controls set in place, with "Other" opening the calendar or month list; the note opens its own page; one button saves). Editing opens on the review page. On phones the overlay is sized to `visualViewport` (`--vvh`/`--vvt`) so it always ends at the keyboard's top edge; keep each page's controls in the top part of the page. `[data-add-spend]` opens it empty, `[data-spend='{json}']` (from `Transaction.as_entry()`) opens it to edit. It posts to the JSON endpoints under `/transactions/`, then re-renders `#page-body` from the current URL with htmx. `/?add=1` opens it (the PWA shortcut). Desktop: type the amount on the keyboard, Enter moves on.

### Templates

- `app/templates/ledger/`: pages, `partials/`, `fragments/` (htmx partial responses).
- `app/templates/cotton/`: django-cotton components (`<c-burrow.habitat>`, `<c-ledger.empty>`, ...).
- Legacy WYGIWYH templates live in the other `app/templates/<app>/` folders and use `layouts/base.html`; don't extend that for ledger pages.

### Frontend

Vite-built; sources in `frontend/src/`, manifest emitted to `app/static_files/manifest.json` and consumed via django-vite. Two entries: `ledger.js` (the app: `styles/ledger.css`, htmx, the entry flow, toasts, theme, charts) and `main.js` (legacy only: Bootstrap, DaisyUI, Alpine, hyperscript, tom-select). The ledger entry is vanilla JS with no `eval` (no Alpine, `htmx.config.allowEval = false`) so the CSP can be enforced later; don't add inline event handlers. Chart.js loads on demand for `<canvas data-chart="budget|funds|fund|inout|income" data-src="<json_script id>">`.

For prod-parity builds, vite runs inside the Dockerfile's `vite_build` stage — no host npm needed. For HMR-style iteration, use the dev compose.

### Burrow design system

The UI follows **Burrow**, the household's shared design system (its own design-system artifact; this app is Cache, Kacang the squirrel's app, which the design system calls "money", so `--accent` is mint). Read the Burrow README before UI work: data stays calm, the animals live at the edges; at most one full-size animal per screen (the Habitat header's; in-card empty states use `<c-ledger.empty>` with a 56px animal or none); pick the animal by job (Kacang = home/budgets/trends, Gali = history/search, Kayu = settings/editing/errors) and the mood by moment.

- **Sources are vendored** in `frontend/burrow/` (`bundle.js`, `bundle.css`, `tokens.json`, copied from the artifact). After updating them run `node frontend/burrow/generate.cjs`, which regenerates `frontend/src/styles/burrow.generated.css` (tokens + `bh-*` classes), `app/static/img/burrow/**` (cast + traces + loader SVGs) and `app/templates/burrow/scenes/*.html` (theme-following inline scenery). Never hand-edit those outputs.
- `frontend/src/styles/ledger.css` is the app's stylesheet on top of the generated one: layout, entry flow, transaction rows, meters, heatmap, forms. Native `<select>` is visible and styled (`.select`). Grid children that hold scrollers need `min-width: 0` (already set for `.cols`, `.stack` and `.form-grid`) or they stretch the page sideways on phones.
- Theme: "match device" by default, or light/dark saved in `localStorage` (`burrow-theme`); an inline script in `<head>` sets `data-theme` (`wygiwyh_light`/`wygiwyh_dark`) before paint.
- **Cotton components** in `templates/cotton/burrow/`: `habitat` (page header band; `kind` oak/burrow/river/meadow), `mascot`, `trace`, `meter` (acorn-capped, `percent` + `over` + `limit`), `stash` (sinking fund, `acorns` 0–15), `wreath` (month ring, `leaves` 0–26). Django can't do inline maths, so callers compute counts in Python (`FundLine.acorns`, `MonthStatus.leaves`) or with `{% widthratio %}`. Cotton `:attr` takes a variable, not an expression.
- **Category icons** are a curated set of Phosphor Icons (Bold, MIT; the Burrow README's choice for icons it doesn't draw). Edit `frontend/icons/library.json` (groups, and the words in a category name that suggest an icon), then run `node frontend/icons/generate.cjs`, which writes `app/static/img/category-icons.svg` (one `<symbol id="i-NAME">` each, used as `<svg><use href="…#i-NAME">`) and `app/apps/ledger/icons.json`. Never hand-edit those outputs. The picker (`partials/icon_picker.html` + `frontend/src/ledger/icons.js`) searches by name and Phosphor's tags.
- Money: `{% money value %}` (`$1,234.50`, `−$5.00` when negative); `{% money t.amount signed=True type=t.type %}` on transaction rows (expense `−`, income `+` in mint). Balances stay unsigned. `{% icon name size %}` draws the Burrow stroke icons.
- Copy: sentence case, verb + object buttons, no emoji; the animals carry the emotion.

### Legacy WYGIWYH apps

`transactions/`, `accounts/`, `currencies/`, `budgets/`, `monthly_overview/`, ... and `api/` are the upstream apps, mounted under `/legacy/`. They still use the `OwnedObject`/`SharedObject` visibility managers and `HOUSEHOLD_MODE` (`docs/MULTI_USER.md`), and their periodic tasks still run. They are kept only so the old data can be imported and compared, and will be removed in a later change; don't build on them. Their tests hit `/legacy/...` paths.

### Charts: |json_script gotcha

Charts are fed by Django's `|json_script`. Pass the **raw dict** to the template — `|json_script` does its own JSON encoding, and passing a pre-stringified blob double-encodes it and the chart silently fails to parse.

## Releases and deploy

Images go to `ghcr.io/theepicflyer/cache`. Two workflows plus a reusable build:

- `ci.yml`: tests on every PR; also called by `release.yml`.
- `release.yml`: on every push to `main`, runs the tests, then `.github/scripts/plan-release.sh` looks at the PRs that push merged. If any carries a `version/*` label it bumps from the latest GitHub release, pushes `:X.Y.Z` + `:latest`, then creates the release **last** (so a release never points at a missing image). No label: it pushes `:nightly` only. `workflow_dispatch` builds a one-off `:<tag>` from any ref.
- `build-push.yml`: the one place the Docker build lives (amd64 only). The image's `org.opencontainers.image.revision` label is the commit it was built from.

### Shipping a change

A release is how work reaches production: the production server polls for new releases, has each one security-reviewed by an agent, and deploys it. So:

- **One PR per piece of work.** If it is too big for one PR, stack PRs with `gh stack` (`gh extension install github/gh-stack`; `gh stack init`, `gh stack add`, `gh stack submit`) and merge the stack together.
- **Exactly one `version/*` label per release**, on the single PR or on the **top** PR of a stack. Leave the lower PRs of a stack unlabeled; one push merging the stack makes one release. If several PRs in one push are labeled, the highest level wins.
  - `version/patch`: fix or chore.
  - `version/minor`: new feature, backward-compatible.
  - `version/major`: breaking change.
  - no label: docs/CI-only or not worth a release (ships `:nightly`, which production ignores).
- **Manual steps go under `## Deploy actions` in the PR description**: a new or changed env var, a one-off management command, data to fix, anything the server can't do by just pulling the image and restarting (migrations run on start). The release job copies these sections into the release notes, and the deployer holds any release whose notes contain that heading until a human does the steps. Omit the heading entirely when there is nothing to do; don't write "None".
- Don't hand-create releases or tags; the workflow does it.

The navbar shows the version baked in at build time (`VERSION` build-arg → `APP_VERSION`).

Destructive or multi-step upgrades also get a playbook entry in `MIGRATIONS.md`, referenced from the PR's Deploy actions.

## Code style notes specific to this fork

- Keep diffs minimum and focused. Prefer editing existing files; don't add new abstractions for single-use code.
- Untranslated user-visible strings should go through `gettext_lazy as _` (`po` files under `app/locale/`).
- htmx-only endpoints **must** carry `@only_htmx` — protects against bare browser navigation rendering a fragment without its frame.
- When adding a new top-level ledger page, wire it through `apps/ledger/urls.py` and add it to both `templates/ledger/partials/rail.html` and `bottom_nav.html` (or reach it from Settings).
