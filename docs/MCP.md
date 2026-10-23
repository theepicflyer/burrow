# MCP adapter (`/mcp`)

WYGIWYH exposes a Model Context Protocol (MCP) endpoint at **`/mcp`** that lets an
MCP client (the Claude Code CLI today; the claude.ai web connector once OAuth
lands — see *Roadmap*) drive the tracker through tools backed by the existing DRF
API. It is a **stateless streamable-HTTP** MCP server provided by
[`django-mcp-server`](https://pypi.org/project/django-mcp-server/) (0.5.7).

Each tool is a thin wrapper over one DRF ViewSet action, so MCP requests run
through the same serializers, validation, ownership, and **per-token scope** as
`/api/`. There is no separate code path with its own rules.

## Authentication

`/mcp` accepts **two** kinds of credential:

1. **`APIToken`** (the Claude Code CLI path) — `Authorization: Token <key>`.
   Create one in the web UI under your account settings.
2. **OAuth 2.1 Bearer token** (the claude.ai web-connector path) —
   `Authorization: Bearer <access-token>`, obtained via the OAuth flow below.

The endpoint itself requires an authenticated, non-demo user
(`NotInDemoMode`, `IsAuthenticated`). The read/write gate is enforced **per tool**
on the underlying ViewSet:

- `TokenScopePermission` for `APIToken`s — a `read_only` token may call `list_*`
  tools but is denied every `create_*` / `update_*` / `delete_*`.
- `OAuthScopePermission` for OAuth tokens — `mcp:read` allows SAFE (read) tools,
  `mcp:write` is required for writes.

Both permissions **no-op for the other credential type** (they sit together in
the DRF default permission stack, which DRF AND-s), so neither path can break the
other.

Unauthenticated requests to `/mcp` get **HTTP 401** with a
`WWW-Authenticate: Bearer resource_metadata="…/.well-known/oauth-protected-resource"`
header that bootstraps the claude.ai OAuth discovery handshake (see below).

## Connecting from claude.ai (OAuth web connector)

Add the tracker as a **custom connector** in claude.ai by URL:

> Settings → Connectors → Add custom connector → URL: `https://<your-host>/mcp`

claude.ai then runs the OAuth 2.1 + PKCE handshake automatically; you only have to
**log in with your existing tracker session** at the consent step. The flow:

1. claude.ai calls `/mcp` unauthenticated → **401** with the `WWW-Authenticate`
   header pointing at the protected-resource metadata.
2. It fetches **`/.well-known/oauth-protected-resource`** (RFC 9728) — which names
   this server as the `resource` and points at the authorization server — then
   **`/.well-known/oauth-authorization-server`** (RFC 8414).
3. The auth-server metadata advertises
   `client_id_metadata_document_supported: true` and
   `token_endpoint_auth_methods_supported: ["none"]`, so claude.ai uses the
   **CIMD** (Client-ID-Metadata-Document) path: its `client_id` is the URL
   `https://claude.ai/oauth/mcp-oauth-client-metadata`. **There is no Dynamic
   Client Registration endpoint** — none is needed.
4. claude.ai redirects you to **`/oauth/authorize/`** with a PKCE **S256**
   challenge and `resource=https://<your-host>/mcp`. The server validates the
   requested `redirect_uri` against the CIMD document (`https://claude.ai/api/mcp/
   auth_callback`) and auto-provisions a public OAuth `Application` for it. The
   CIMD fetch is SSRF-hardened: it requires `https`, refuses to follow redirects,
   and rejects any `client_id` host that resolves to a private/loopback/link-local/
   reserved address (fail-closed). The `MCP_CIMD_ALLOW_PRIVATE_HOSTS` setting
   (default `False`) relaxes only the private-IP block for local test fixtures.
5. You **log in / consent** with your existing tracker session. The server issues
   an authorization code, which claude.ai exchanges at **`/oauth/token/`** (public
   client, **no secret**, with the PKCE `code_verifier`) for a Bearer access token
   carrying `mcp:read mcp:write`.
6. Every subsequent `/mcp` call uses `Authorization: Bearer <token>`.

**Audience binding (RFC 8707):** if a `resource` parameter is sent it MUST equal
the exact `/mcp` URL you entered in claude.ai; a mismatch is rejected
(`400 invalid_target`) so a token can never be minted for a different audience.

The OAuth pieces live in `app/apps/mcp/oauth.py` (discovery metadata, CIMD client
resolution, audience check) and `app/apps/mcp/permissions.py` (scope enforcement);
`django-oauth-toolkit` supplies the authorize/token endpoints, PKCE and token
storage. Only `/oauth/authorize/` and `/oauth/token/` are mounted — none of DOT's
application-management UI or OIDC discovery is exposed.

## Connecting from the Claude Code CLI

```sh
claude mcp add --transport http wygiwyh https://burrow.example.com/mcp \
  --header "Authorization: Token <key>"
```

Then list tools / use them from a Claude Code session. For a local dev stack the
URL is `http://localhost:<port>/mcp`.

> **Write-access risk — read this before using a `read_write` token.**
> The write tools give an LLM full CRUD over your ledger: it can create, modify,
> and **permanently delete** transactions, accounts, budgets, and more. On
> `currencies` and `exchange_rates` in particular, a single bad write can
> silently corrupt every multi-currency figure in the app (balances, net worth,
> reports) without an obvious error. **Connect with a `read_only` token unless
> you specifically intend the model to make changes**, and review any proposed
> writes. Deletes are not soft-deletes at the API level — they are gone.

## Tool surface

Registration is data-driven in `app/apps/mcp/mcp.py` (a list of resources, not
~55 hand-written calls). Names are snake_case: **plural for list, singular for
writes**.

**13 ledger ViewSets — full CRUD** (`list_*`, `create_*`, `update_*`,
`delete_*` each):

| Resource | list / create / update / delete |
| --- | --- |
| transactions | `list_transactions` / `create_transaction` / `update_transaction` / `delete_transaction` |
| categories | `list_categories` / `create_category` / `update_category` / `delete_category` |
| tags | `list_tags` / `create_tag` / `update_tag` / `delete_tag` |
| entities | `list_entities` / `create_entity` / `update_entity` / `delete_entity` |
| installment plans | `list_installment_plans` / `create_installment_plan` / … |
| recurring transactions | `list_recurring_transactions` / `create_recurring_transaction` / … |
| account groups | `list_account_groups` / `create_account_group` / … |
| accounts | `list_accounts` / `create_account` / … |
| currencies | `list_currencies` / `create_currency` / … |
| budgets | `list_budgets` / `create_budget` / … |
| exchange rates | `list_exchange_rates` / `create_exchange_rate` / … |
| DCA strategies | `list_dca_strategies` / `create_dca_strategy` / … |
| DCA entries | `list_dca_entries` / `create_dca_entry` / … |

**2 import ViewSets — read-only** (`list_*` only): `list_import_profiles`,
`list_import_runs`.

**Total: 54 tools** (13 × 4 + 2).

### Notable omissions

- **No `retrieve` tool.** `django-mcp-server` has no retrieve publisher, so
  there is no "get one by id" tool. Use `list_*` with the ViewSet's query
  filters to find a record (and its id); `update_*` / `delete_*` take that id.
- **`ImportViewSet` is not exposed at all.** It is a plain `ViewSet` whose only
  action is `create`, which triggers an asynchronous file import and writes an
  `ImportRun`. It has no safe `list` action, so it is skipped entirely rather
  than exposing an import-trigger write tool.

### `update_*` is PUT, not PATCH

Update tools call the ViewSet's `update` (HTTP PUT), so the `body` must contain
**all required fields**, not just the ones being changed — a partial body will
fail validation on the missing required fields. Each update tool's instructions
state this.

### Input schemas (`body_schema`)

This DRF version doesn't expose the schema hook `django-mcp-server` expects, so
the library would otherwise advertise an empty generic `body` for write tools
(it logs a boot-time CRITICAL when it falls back). To keep the write tools
usable, `app/apps/mcp/schema.py` derives a JSON Schema per resource from its DRF
serializer — walking `serializer().get_fields()`, skipping read-only fields,
typing each field, and marking required ones — and we pass it as `body_schema=`.
Custom relational fields (the tag/category/entity "id-or-name" fields) carry
their own schema via `@extend_schema_field`, which the deriver reads. Fields it
can't classify degrade to an untyped `{}` rather than failing. With explicit
schemas supplied for all create/update tools, no CRITICAL is logged at boot.

## The django-mcp-server shim (why the library is monkeypatched)

`app/apps/mcp/mcp.py` installs `_patch_initialize_request_for_body()`, a one-
staticmethod monkeypatch of `BaseAPIViewCallerTool._patched_initialize_request`.

The library (0.5.7) drops the request body on the way into create/update tools:
it builds an inner request carrying the tool `body` but then throws it away and
returns the **outer** JSON-RPC request, whose `.data` is the `tools/call`
envelope rather than the create fields — so DRF reports the fields as missing and
no row is written. The shim keeps the body-carrying inner request **and** forwards
the caller's authenticated `APIToken` (`_force_auth_user` / `_force_auth_token`)
onto it before running the genuine `APIView.initialize_request`, so `.data` parses
the body and `TokenScopePermission` still sees the real token and method. It
patches one staticmethod once and applies to every registered tool; it does not
fork or vendor the library. Full rationale is in the `mcp.py` module docstring.

**If you bump `django-mcp-server`, re-verify the shim still applies** (the body-
plumbing bug it works around may be fixed or moved upstream).

## Migrations / deploy note

The OAuth path adds the `oauth2_provider` app, which ships its own migrations
(Application / AccessToken / Grant / RefreshToken tables). Run `migrate` on
deploy — see the `MIGRATIONS.md` entry. No project-level migrations are added.
