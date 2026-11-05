# MCP server (`/mcp`)

Burrow exposes a Model Context Protocol (MCP) endpoint at **`/mcp`** so an agent
(claude.ai custom connector, Claude Code CLI, or any MCP client) can read the
household ledger and, with write access, log spends. It is a **stateless
streamable-HTTP** server built on
[`django-mcp-server`](https://pypi.org/project/django-mcp-server/). The tools are a
hand-written `MCPToolset` in `app/apps/ledger/mcp.py` over the ledger models and
`apps.ledger.services`, so agents see the same numbers as the app.

## Authentication

`/mcp` accepts:

1. **`APIToken`**: `Authorization: Token <key>`. Create one in the app under
   Settings → Agents (MCP); it is shown once. Scope is read only or read and write.
2. **OAuth 2.1 Bearer token**: `Authorization: Bearer <access-token>`, from the
   OAuth flow below (the claude.ai path). Scopes are `mcp:read` and `mcp:write`.
3. A signed-in browser session or a DRF authtoken (full access, as on `/api/`).

Every tool requires a signed-in user. Each tool checks scope itself before it runs
(`access_error` in `apps/ledger/mcp.py`): read tools need `mcp:read` on an OAuth
token, write tools need a read-and-write `APIToken` or `mcp:write`.
`LedgerTools._add_tools_to` refuses to register a tool that skips this check.

Unauthenticated requests get **HTTP 401** with a
`WWW-Authenticate: Bearer resource_metadata="…/.well-known/oauth-protected-resource"`
header that starts the claude.ai OAuth discovery handshake.

The ledger is shared: every signed-in user sees all of it, so tools do no
per-user filtering.

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
   `https://claude.ai/oauth/mcp-oauth-client-metadata`.
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
resolution, Dynamic Client Registration, audience check) and `app/apps/mcp/permissions.py` (scope enforcement);
`django-oauth-toolkit` supplies the authorize/token endpoints, PKCE and token
storage. Only `/oauth/authorize/`, `/oauth/token/` and `/oauth/register/` are mounted — none of DOT's
application-management UI or OIDC discovery is exposed.

### Clients without CIMD (Dynamic Client Registration)

Clients that don't support CIMD, such as Meta's Muse agent, register through
**`POST /oauth/register/`** (RFC 7591), which the auth-server metadata advertises
as `registration_endpoint`. The rest of the flow (steps 4–6) is the same.

An open registration endpoint would let any site register a client and receive
authorization codes, so registration only accepts redirect URIs on the
`MCP_DCR_ALLOWED_REDIRECT_URIS` setting (space-separated env var). The default
covers claude.ai, claude.com, Meta Muse and loopback:

```
https://claude.ai/api/mcp/auth_callback https://claude.com/api/mcp/auth_callback https://agent.meta.ai/api/hatch/oauth/callback http://localhost:* http://127.0.0.1:*
```

A trailing `:*` matches any port and path on that scheme and host. Setting the
variable replaces the default, so include the defaults you still want. Every
registered client is public (no secret) and must use PKCE; a request for a
confidential client is answered with a public one.

## Connecting from the Claude Code CLI

```sh
claude mcp add --transport http burrow https://burrow.example.com/mcp \
  --header "Authorization: Token <key>"
```

Then list tools / use them from a Claude Code session. For a local dev stack the
URL is `http://localhost:<port>/mcp`.

> **Write access.** A `read_write` token (or an OAuth connection granted
> `mcp:write`) lets the model add, edit and **permanently delete** spends. Use
> `read_only` unless you want the agent to log spends, and review what it
> proposes.


## Tools

Amounts are 2-decimal strings, dates `YYYY-MM-DD`, months `YYYY-MM`. A spend is a
positive amount; a negative amount is money back (a refund, or money put into a
fund). `date` is when it happened; `month` is the month it counts toward. Every
tool except `get_ledger_info` first creates any recurring entries that have
fallen due.

Read:

| Tool | What it returns |
| --- | --- |
| `get_ledger_info` | Currency, today, the current month, who is signed in, whether writes are allowed, and what the fields mean. |
| `list_categories` | Categories with kind (budget or fund), this month's amount, and for funds the balance and target. |
| `list_transactions` | A page of transactions (filter by `month`, `date_from`/`date_to`, `category_id`, `search`), the total count and total amount. Limit is capped at 500. |
| `get_month_summary` | Per budget category: budget, spent, left, over. Per fund: top-up, spent, month-end balance. Pace for the current month. |
| `get_budget_analysis` | Per category per month budget and spent, months over, averages, `consistently_over`; monthly totals; fund balance series. Running months are `partial` and left out of counts. |
| `list_recurring` | Recurring rules with schedule, next date and the month that entry will count toward. |

Write (needs write scope):

| Tool | What it does |
| --- | --- |
| `add_transaction` | Adds a spend. `date` defaults to today, `month` to the date's month. |
| `update_transaction` | Partial update of one transaction. |
| `delete_transaction` | Deletes one transaction. |

There are no tools for editing categories, monthly amounts or recurring rules;
do those in the app.

Bad input (unknown category, bad date, zero amount, more than 2 decimals) comes
back as an MCP error result with a message the agent can act on.
