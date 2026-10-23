# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Burrow is a personal finance tracker, published at `github.com/theepicflyer/burrow` (public, AGPL-3.0). It is a **hard fork** of `eitchtee/WYGIWYH`: upstream history is kept up to the fork point, but upstream is not tracked or merged. Internal names still say WYGIWYH (the `app/WYGIWYH/` Django project, `wygiwyh` DB/user, `wygiwyh_*` theme keys); leave them, renaming them buys nothing and breaks existing deployments. User-visible text says Burrow, and the README credits WYGIWYH.

The main additions are **Budgets & Funds** (see `app/apps/budgets/`): a sinking-fund model layered on top of the upstream transaction model, plus monthly budget rows that auto-materialize income for sinking categories.

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

`docker-compose.prod.yml` is the example compose for self-hosters (pulls `ghcr.io/theepicflyer/burrow:latest`, bind-mounts `./postgres_data`); do not run it locally.

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
docker run -d --rm --name burrow-test-pg -e POSTGRES_USER=wygiwyh -e POSTGRES_PASSWORD=test -e POSTGRES_DB=wygiwyh -p 127.0.0.1:55432:5432 postgres:15-bookworm
npm ci --prefix frontend && npm run build --prefix frontend
cd app && export SECRET_KEY=test SQL_DATABASE=wygiwyh SQL_USER=wygiwyh SQL_PASSWORD=test SQL_HOST=127.0.0.1 SQL_PORT=55432
uv run python manage.py collectstatic --noinput
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test --parallel auto
```

Add tests next to the app (`app/apps/<app>/tests/`) for new behaviour. For UI changes also exercise the affected pages. If the Claude-in-Chrome MCP integration is connected (`list_connected_browsers` returns a device), drive verification through it: navigate to the affected URL, screenshot, optionally check console errors. The user must log into the running stack themselves; the session cookie then persists for the rest of the agent loop.

### Python tooling

`uv` only. Never `source venv/bin/activate`. For host-side scripts: `uv run python …`. Lockfile is `uv.lock`; bump deps via `uv add`/`uv lock --upgrade`.

## .env

Single `.env` at repo root, loaded by all compose files. Two gotchas:
- `DJANGO_ALLOWED_HOSTS` is **space-separated**, not comma-separated (`settings.py:36`).
- `.env` is gitignored; `.env.example` is the template. For local work, ensure `localhost 127.0.0.1` are in `DJANGO_ALLOWED_HOSTS`.

## Architecture

Django 5.2 + DRF + htmx + django-cotton + Vite for assets. Backed by Postgres 15 and Procrastinate for async jobs (runs in-process via supervisord in the single-container deploy).

### Apps layout (`app/apps/`)

Each app is a Django app under `apps.<name>`. The key ones:

- **`transactions/`** — core ledger model (`Transaction`, `TransactionCategory`, `TransactionTag`). Everything else dangles off transactions.
- **`accounts/`** — financial accounts (banks, wallets, brokerages). Distinct from `users/`.
- **`currencies/`** — multi-currency support and exchange rates. Currencies are user-defined; custom ones (crypto, points) are first-class.
- **`budgets/`** — this fork's main addition. See *Budgets & funds* below.
- **`monthly_overview/`, `yearly_overview/`, `calendar_view/`, `net_worth/`, `insights/`, `dca/`** — view-layer apps consuming the ledger. Heavy htmx use; templates live under `app/templates/<app>/`.
- **`api/`** — DRF endpoints + drf-spectacular schema (`/api/`, `/api/docs/`).
- **`import_app/`, `export_app/`, `rules/`** — bulk operations and the user-defined transaction-rewriting rule engine.
- **`common/`** — shared base models (`OwnedObject`, `SharedObject`), the `@only_htmx` decorator (`apps/common/decorators/htmx.py`), htmx-aware auth.

### Ownership and sharing

Most user-facing models extend `OwnedObject` or `SharedObject` from `apps/common/models.py`. `SharedObjectManager` is the default `objects` manager and applies the visibility filter (owner + `shared_with`). Use `Model.all_objects` (a vanilla `Manager`) when you need to bypass that, e.g. write paths that explicitly set `owner`. Forgetting this is the most common source of mystery empty querysets.

`HOUSEHOLD_MODE` (env, off by default) makes every signed-in user a co-owner of all data: every visibility manager short-circuits through `in_household(user)` and views check `can_manage(obj, user)` instead of comparing `owner` to `request.user`. A new manager or owner-only check must go through these two helpers. See `docs/MULTI_USER.md`.

### Templates

- `app/templates/<app>/pages/` — full-page templates rendered by `GET`.
- `app/templates/<app>/fragments/` — htmx partial responses; view fns are decorated with `@only_htmx` and return one fragment.
- `app/templates/cotton/` — django-cotton components, used as `<c-foo.bar />` in pages.
- `app/templates/includes/sidebar.html` — primary navigation; add new top-level entries here.

### Frontend

Vite-built; sources in `frontend/src/`, manifest emitted to `app/static_files/manifest.json` and consumed via django-vite. For prod-parity builds, vite runs inside the Dockerfile's `vite_build` stage — no host npm needed. For HMR-style iteration, use the dev compose.

**Native `<select>` is globally hidden** (`select { display:none }` in `styles/style.scss`, to avoid flicker before enhancement). Any visible dropdown must be a tom-select: put the `<select>` inside an element carrying `_="install init_tom_select"` (see `extends/offcanvas.html`); the behavior strips `.select` and builds a `.ts-wrapper`. A bare `<select>` renders invisibly with no error — easy to miss.

### Burrow design system

The UI follows **Burrow**, the household's shared design system (its own design-system artifact; this app is "money", Kacang the squirrel's app, so `--accent` is mint). Read the Burrow README before UI work: data stays calm, the animals live at the edges; at most one full-size animal per screen; pick the animal by job (Kacang = budgets/money, Gali = history/search/empty/loading, Kayu = settings/editing/errors) and the mood by moment.

- **Sources are vendored** in `frontend/burrow/` (`bundle.js`, `bundle.css`, `tokens.json`, copied from the artifact). After updating them run `node frontend/burrow/generate.cjs`, which regenerates `frontend/src/styles/burrow.generated.css` (tokens + `bh-*` classes), `app/static/img/burrow/**` (cast + traces + loader SVGs) and `app/templates/burrow/scenes/*.html` (theme-following inline scenery). Never hand-edit those outputs.
- **DaisyUI is restyled, not replaced.** `tailwind.css` points the `wygiwyh_light`/`wygiwyh_dark` theme slots at Burrow values (fills like `primary`/`success` are the bright tokens with `on-accent` text); `frontend/src/styles/burrow.css` holds the app-side overrides in `@layer utilities` (sticker buttons, fields, cards) and app components (`.bh-txn` rows, `.bh-kpi`, bottom nav). Text that carries meaning uses the `*-text` tokens: `.text-success`/`.text-income` → `--mint-text`, `.text-error`/`.text-negative` → `--tomato-text`; money out (`.text-expense`) stays ink.
- **Cotton components** in `templates/cotton/burrow/`: `habitat` (page header band; `kind` oak/burrow/river/meadow), `mascot`, `trace`, `meter` (acorn-capped, `percent` + `over`), `stash` (sinking fund, `acorns` 0–15), `wreath` (month ring, `leaves` 0–26). `c-msg.empty` is the Burrow EmptyState (default Gali sleepy; pass `who`/`mood`). Django can't do inline maths, so callers compute counts with `{% widthratio value max N as x %}` and pass `:x`.
- Amounts: `c-amount.display` only adds a `+`/`−` sign when given `signed` (transaction rows); balances stay unsigned.
- Charts: `charts.js` sets Burrow fonts/grid/tooltip defaults and colours any dataset that brings no colours of its own; use `burrowColors()`, `burrowSeries()` and `burrowAlpha(hex, a)` instead of hard-coded hex.
- Copy: sentence case, verb + object buttons, no emoji; the animals carry the emotion.

## Budgets & funds (current work area)

Layered on top of transactions; lives entirely in `app/apps/budgets/`. Note: the old `Fund`
model was removed in `669ec8ed` — "funds" are now just **`Account`s with `kind == SINKING`**
(vs `NORMAL`), and a `TransactionCategory` belongs to a fund via its `account` FK.

This app is multi-user/sharing-aware: scoping always goes through the sharing-aware default
managers (thread-local current user), never `owner=` filters. `Budget` visibility specifically
follows its category (`BudgetManager`, not the row's own owner). See `docs/MULTI_USER.md` for
household setup — a second login via Pocket ID OIDC plus `HOUSEHOLD_MODE` (or per-object sharing).

- **`Budget`** (`models.py`): `(category, month, amount)`, month always day=1. For
  **sinking-account categories** this is the monthly auto-allocation override; for
  **normal-account categories** it's the planned budget. `_budget_for(category, month)` in
  `services/monthly.py` is the canonical lookup: explicit `Budget` row if present, else
  `category.monthly_default_amount`.
- **`tasks.py`** — `materialize_for_month()` (periodic, 1st of month) auto-creates a muted paired
  allocation per sinking-account category: EXPENSE on the owner's Main account + INCOME on the
  sinking account. Idempotent via a description marker.
- **`services/monthly.py`** — `monthly_status()` → `CategoryStatus` rows (budget/spent/received/
  carryover/balance) consumed by the `monthly_budget_status` fragment (the "Budget" tab on the
  monthly-overview page).
- **`services/analysis.py`** — `budget_analysis(user, year, month, months=12)` → current-month
  KPIs + per-normal-category budget levels (reuses `monthly_status`), a normal budget-vs-spent
  trend, and a per-sinking-fund running-balance series. Consumed by the **Budget Analysis** page
  (`budgets_analysis` view, `/budgets/analysis/`, `templates/budgets/pages/analysis.html`). The
  trend ships per-category series too (`trend.all` + `trend.categories[]`); a tom-select dropdown
  swaps the chart client-side via `Chart.getChart('budgetTrendChart')` (no stored binding — a
  top-level `let`/`const` would throw "already declared" when the inline script re-runs on
  hx-boost month nav). Each budget-level row links to `budget_category_transactions`
  (`@only_htmx`), an offcanvas read-only preview of that category's transactions for the month —
  filtered on `reference_date` so its EXPENSE total reconciles with the bar's `spent`.

Normal vs sinking answer **different questions** — normal = "did spend stay under budget"
(spent vs `Budget.amount`); sinking = "what's the fund balance" (carryover + received − spent,
accumulating). Keep them visually/semantically split; don't build a single budget-vs-actual
chart that lumps them. Amounts are summed raw across currencies (no per-currency split yet) —
the analysis page surfaces this with a note only when >1 currency is in use.

### Budget-editor invariant

`/budgets/edit/` (`budgets_edit` view) edits `TransactionCategory.monthly_default_amount`. On save, past months are **backfilled** with the OLD default into explicit `Budget` rows (via `get_or_create`, never overwriting an existing explicit row) so that changing the default only affects the **current and future** months. Preserve this invariant when touching that view.

### Charts: |json_script gotcha

Budget charts use Chart.js (`window.Chart`, see `frontend/src/js/charts.js`) fed by Django's
`|json_script`. Pass the **raw dict** to the template — `|json_script` does its own JSON
encoding, and passing a pre-stringified blob double-encodes it and the chart silently fails to
parse. See `views.budgets_analysis` → `analysis.html` (`budgetTrendData` / `sinkingData`).

## Releases and deploy

Images go to `ghcr.io/theepicflyer/burrow`. Two workflows plus a reusable build:

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
- When adding a new top-level page, wire it through `apps/<app>/urls.py` and add the sidebar entry in `app/templates/includes/sidebar.html`.
