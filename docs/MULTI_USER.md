# Multi-user setup: a second login on shared data

This tracker is single-owner by default: every object has an `owner` and is
private unless explicitly shared. This doc covers giving a second person
their own login — authenticated via Pocket ID (self-hosted OIDC at
`https://auth.example.com`) — while both of you see and edit the same
household data.

## 1. Pocket ID (OIDC) login

OIDC is wired up purely through env vars read in `app/WYGIWYH/settings.py`
(~L361-390): if `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `OIDC_SERVER_URL`
are all set, an `openid_connect` provider app is registered with
django-allauth. `provider_id` is `slugify(OIDC_CLIENT_NAME)` — for
`OIDC_CLIENT_NAME="Pocket ID"` that's `pocket-id`.

### Create the OIDC client in Pocket ID

In Pocket ID, create a new OIDC client for this app and set its callback/redirect
URI to:

```
https://<app-host>/auth/oidc/pocket-id/login/callback/
```

This is derived from how the URLs are actually mounted: `app/WYGIWYH/urls.py`
mounts `path("auth/", include("allauth.urls"))`; allauth's own url root then
nests every social/OIDC provider under `oidc/` (the
`OPENID_CONNECT_URL_PREFIX` setting, default `"oidc"`, unless it's ever
overridden — check `settings.py` if this doc ever drifts), then
`<provider_id>/login/callback/` (the `openid_connect` provider's
`urls.py`). So: `auth/` + `oidc/` + `pocket-id/` + `login/callback/`.

Note the client ID and secret Pocket ID gives you — they go in the next step.

### Configure env vars

Add to the prod `.env` (the single repo-root `.env`, loaded by all compose
files):

```sh
OIDC_CLIENT_NAME="Pocket ID"
OIDC_CLIENT_ID=<client id from Pocket ID>
OIDC_CLIENT_SECRET=<client secret from Pocket ID>
OIDC_SERVER_URL=https://auth.example.com
OIDC_ALLOW_SIGNUP=true
```

`OIDC_SERVER_URL` must be Pocket ID's OIDC issuer/discovery base (allauth's
`openid_connect` provider does OIDC discovery from it — point it at the
issuer, not a specific endpoint).

Then recreate the web container so settings re-read the env (no migration or
new image needed — this is pure configuration):

```sh
docker compose up -d web
```

(Locally, that's `docker compose -f docker-compose.local.yml up -d --build web`.)

### What happens on login

`app/templates/users/login.html` calls allauth's `{% get_providers %}` and
renders a "Login with Pocket ID" button automatically for every configured
provider — no template change needed. The existing email+password form still
renders above it, so your own login keeps working unchanged.

**Connecting to an existing account (you):** `apps/users/adapters.py`'s
`AutoConnectSocialAccountAdapter` auto-connects an incoming OIDC login to an
existing local user **by matching email** (`User.objects.get(email__iexact=email)`).
This only works if your Burrow account's email is *exactly* the same as your
Pocket ID account's email. Since Pocket ID is self-hosted, its emails are
whatever you set them to be — there's no third-party verification step to
worry about, but you still need the two to match character-for-character
before either of you first logs in via OIDC.

**First-time signup (second user):** if they don't already have a Burrow account with
a matching email, their first Pocket ID login auto-creates one — gated by
`SOCIALACCOUNT_AUTO_SIGNUP`, which reads `OIDC_ALLOW_SIGNUP` (default
`true`). Once they've signed up, consider setting `OIDC_ALLOW_SIGNUP=false` in
`.env` and restarting the web container, so no other Pocket ID account can
silently create a new Burrow user.

## 2. Sharing everything with a second user

A fresh second account owns nothing and sees nothing except objects marked `visibility="public"`. There are two ways to get both logins onto the same data.

### Option A — household mode (recommended for a household)

Set `HOUSEHOLD_MODE=true` in `.env` and restart the web container. Every signed-in user then sees and can edit, delete and re-share everything: accounts, account groups, categories, tags, entities, transactions (including recurring, installment and quick transactions), budgets, rules and DCA strategies. New objects need no sharing, and there is nothing to backfill.

How it works: `in_household(user)` in `apps/common/models.py` short-circuits every visibility manager (`SharedObjectManager`, `OwnedObjectManager`, the transaction managers, `BudgetManager`) to return all rows, and `can_manage(obj, user)` replaces the owner-only checks in the edit/delete/share views. The Share button is hidden. `owner` is still recorded, so it shows who created a row. Per-user view preferences such as untracking an account stay per user.

Only turn this on when every account on the instance belongs to the household: it treats any signed-in user as a co-owner. Lock signup down (`OIDC_ALLOW_SIGNUP=false`, or restrict who can use the Burrow client in your IdP) so nobody else can join.

A member who owns no accounts of their own (typical for the second login) gets the first visible Main account as the default when entering a transaction.

### Option B — per-object sharing

Leave `HOUSEHOLD_MODE` off and share objects explicitly. Each shareable object (accounts, account groups, categories, tags, entities, rules, DCA strategies) extends `SharedObject` (`apps/common/models.py`): an `owner`, a `visibility` (`private`/`public`) and a `shared_with` M2M. Transactions follow their account's sharing and budgets follow their category's, so they need nothing extra. Shared users can view and use an object, but only its owner can edit or delete it, and recurring, installment and quick transactions stay owner-only.

Share one object at a time with the Share button in each list, or backfill everything with a one-off script in `docker compose exec web python manage.py shell`:

```python
from django.contrib.auth import get_user_model
from apps.accounts.models import Account, AccountGroup
from apps.transactions.models import TransactionCategory, TransactionTag, TransactionEntity
from apps.rules.models import TransactionRule
from apps.dca.models import DCAStrategy

User = get_user_model()
user_a = User.objects.get(email="you@example.com")
user_b = User.objects.get(email="partner@example.com")

# all_objects: there is no thread-local user in a shell, so `objects` would only return public rows.
for model in [Account, AccountGroup, TransactionCategory, TransactionTag, TransactionEntity, TransactionRule, DCAStrategy]:
    for owner, other in ((user_a, user_b), (user_b, user_a)):
        for obj in model.all_objects.filter(owner=owner):
            obj.shared_with.add(other)
```

It only adds shares and is safe to re-run. New objects start private, so re-run it (or share by hand) as you add things.

## 3. How the budgets app fits in

`Budget` rows (`apps/budgets/models.py`) are unique per `(category, month)`
and have no sharing fields of their own — `BudgetManager` (the `objects`
manager) filters by the **category's** visibility (`category__owner`,
`category__shared_with`, `category__visibility`), so once a
`TransactionCategory` is shared with the second user, every `Budget` row for that category
is visible to them automatically; nothing extra to share. (Note: `Budget`'s
*default* manager is actually `all_objects`, declared first in the model so
reverse relations keep working unfiltered — `services/monthly.py` and
`services/analysis.py` use it directly and do their own user-scoping via the
categories/accounts they've already fetched through the sharing-aware
managers.)

The monthly-status and budget-analysis pages (`services/monthly.py`,
`services/analysis.py`) aggregate over all *visible* accounts and categories
for the requesting user — with household mode on, or once accounts and
categories are shared per Option B, both logins compute identical budget
numbers from the same underlying transactions.
