"""Bespoke OAuth 2.1 glue for the claude.ai MCP connector.

All the hand-built OAuth pieces that ``django-oauth-toolkit`` (DOT) does not
ship live here, in one auditable place, so the security-critical surface is a
single file. DOT provides the OAuth 2.1 core (PKCE, the authorize/token
endpoints, token storage); this module adds the four things the MCP
connector handshake needs on top:

1. **Discovery metadata** -- RFC 9728 protected-resource metadata and RFC 8414
   authorization-server metadata, served as plain JSON with no auth, with the
   flags that make claude.ai pick the CIMD (client-id-metadata-document) path
   and never probe a (non-existent) Dynamic Client Registration endpoint.

2. **The 401 challenge** -- an unauthenticated ``/mcp`` request returns
   ``401`` with ``WWW-Authenticate: Bearer resource_metadata="..."`` so the
   client knows where to start discovery. (Wired on the view in ``urls.py``.)

3. **CIMD client resolution** -- when ``client_id`` is a URL (claude.ai's is
   ``https://claude.ai/oauth/mcp-oauth-client-metadata``), validate the
   requested ``redirect_uri`` with the same two-branch logic Home Assistant's
   ``indieauth.verify_redirect_uri`` uses, then auto-provision a public DOT
   ``Application`` so the rest of DOT's flow works unchanged. This replaces an
   open Dynamic Client Registration endpoint.

4. **Audience validation** (RFC 8707) -- the ``resource`` parameter, if sent,
   must equal this MCP server's canonical URI.

The OAuth read/write **scope** enforcement on tool dispatch lives next door in
``apps.mcp.permissions`` (it has to sit in the DRF default permission stack).
"""

from __future__ import annotations

import ipaddress
import json
import socket
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from oauth2_provider.models import get_application_model
from oauth2_provider.oauth2_validators import OAuth2Validator

# claude.ai's CIMD document lives on a different host+path than its redirect
# callback, so the fast path never matches and the CIMD fetch branch runs.
_CIMD_TIMEOUT_SECONDS = 5
_CIMD_MAX_BYTES = 10 * 1024

OAUTH_SCOPES = {
    "mcp:read": "Read your tracker data",
    "mcp:write": "Create, modify and delete your tracker data",
}


# ---------------------------------------------------------------------------
# Canonical URLs (built from the request so they honour the deployed scheme
# and host -- SECURE_PROXY_SSL_HEADER makes request.scheme correct behind the
# prod reverse proxy).
# ---------------------------------------------------------------------------
def mcp_resource_uri(request) -> str:
    """The MCP server's canonical resource URI -- the URL the user types into
    claude.ai. The audience (RFC 8707 ``resource``) MUST equal this exactly."""
    return request.build_absolute_uri(reverse("mcp_server_streamable_http_endpoint"))


def protected_resource_metadata_url(request) -> str:
    return request.build_absolute_uri("/.well-known/oauth-protected-resource")


def resource_param_ok(request) -> bool:
    """RFC 8707 audience check: if a ``resource`` parameter is present it MUST
    equal this MCP server's canonical URI. Absent ``resource`` is allowed
    (older clients) -- presence with a mismatch is rejected so a token can
    never be minted for a different audience."""
    resource = request.GET.get("resource") or request.POST.get("resource")
    if not resource:
        return True
    return resource == mcp_resource_uri(request)


def www_authenticate_value(request) -> str:
    """The exact ``WWW-Authenticate`` header value for an unauthenticated
    ``/mcp`` request. This kicks off the claude.ai discovery handshake."""
    return f'Bearer resource_metadata="{protected_resource_metadata_url(request)}"'


# ---------------------------------------------------------------------------
# Discovery metadata documents (no auth -- these are public by spec).
# ---------------------------------------------------------------------------
@csrf_exempt
def protected_resource_metadata(request, *args, **kwargs):
    """RFC 9728 OAuth 2.0 Protected Resource Metadata.

    Served at both ``/.well-known/oauth-protected-resource`` and the
    path-suffixed ``/.well-known/oauth-protected-resource/mcp`` (claude.ai
    probes the suffixed one first)."""
    return JsonResponse(
        {
            "resource": mcp_resource_uri(request),
            "authorization_servers": [request.build_absolute_uri("/")[:-1]],
            "scopes_supported": ["mcp:read", "mcp:write"],
            "bearer_methods_supported": ["header"],
            "resource_documentation": request.build_absolute_uri("/api/docs/"),
        }
    )


@csrf_exempt
def authorization_server_metadata(request, *args, **kwargs):
    """RFC 8414 OAuth 2.0 Authorization Server Metadata.

    The two CIMD flags are load-bearing: ``client_id_metadata_document_
    supported`` plus ``token_endpoint_auth_methods_supported: ["none"]`` make
    claude.ai deterministically use a URL ``client_id`` (CIMD) and never DCR-
    probe a missing ``/register`` endpoint."""
    return JsonResponse(
        {
            "issuer": request.build_absolute_uri("/")[:-1],
            "authorization_endpoint": request.build_absolute_uri(
                reverse("oauth2_provider:authorize")
            ),
            "token_endpoint": request.build_absolute_uri(
                reverse("oauth2_provider:token")
            ),
            "scopes_supported": ["mcp:read", "mcp:write"],
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "client_id_metadata_document_supported": True,
        }
    )


# ---------------------------------------------------------------------------
# CIMD redirect-uri validation (mirrors HA indieauth.verify_redirect_uri).
# ---------------------------------------------------------------------------
def _same_scheme_and_host(client_id: str, redirect_uri: str) -> bool:
    """Fast path: a client whose ``client_id`` and ``redirect_uri`` share a
    scheme and host is implicitly trusted (the redirect stays on its origin)."""
    c = urlsplit(client_id)
    r = urlsplit(redirect_uri)
    return bool(c.scheme) and c.scheme == r.scheme and c.netloc == r.netloc


def _assert_host_not_internal(host: str) -> None:
    """SSRF guard: resolve ``host`` and reject if *any* resolved address is
    private / loopback / link-local / multicast / reserved / unspecified. Also
    rejects a host that does not resolve. Raises ``ValueError`` on rejection.

    The ``MCP_CIMD_ALLOW_PRIVATE_HOSTS`` Django setting (default ``False``)
    skips this block so local/dev fixtures on localhost can be tested; prod
    leaves it False and stays strict. Never enable it in committed settings."""
    if getattr(settings, "MCP_CIMD_ALLOW_PRIVATE_HOSTS", False):
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"client_id host does not resolve: {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(f"client_id resolves to a disallowed address: {ip}")


def _fetch_cimd_redirect_uris(client_id: str) -> list[str]:
    """CIMD fetch branch: GET the ``client_id`` URL, parse the JSON client-
    metadata document, return its registered ``redirect_uris``.

    SSRF hardening: the URL must be **https**; its host must not resolve to any
    internal address (see ``_assert_host_not_internal``); redirects are NOT
    followed (a 3xx is treated as a failed fetch -- it is an SSRF bypass
    vector). Bounded by a short timeout and a small body cap."""
    parts = urlsplit(client_id)
    if parts.scheme != "https":
        raise ValueError("CIMD client_id must be https")
    if not parts.hostname:
        raise ValueError("CIMD client_id has no host")
    _assert_host_not_internal(parts.hostname)
    resp = requests.get(
        client_id,
        timeout=_CIMD_TIMEOUT_SECONDS,
        stream=True,
        allow_redirects=False,
        headers={"Accept": "application/json"},
    )
    if resp.is_redirect or resp.is_permanent_redirect:
        raise ValueError("CIMD fetch returned a redirect (not followed)")
    resp.raise_for_status()
    body = resp.raw.read(_CIMD_MAX_BYTES + 1, decode_content=True)
    if len(body) > _CIMD_MAX_BYTES:
        raise ValueError("client metadata document too large")
    doc = json.loads(body.decode("utf-8"))
    uris = doc.get("redirect_uris")
    if not isinstance(uris, list):
        raise ValueError("client metadata document has no redirect_uris list")
    return [u for u in uris if isinstance(u, str)]


def verify_redirect_uri(client_id: str, redirect_uri: str) -> bool:
    """Validate ``redirect_uri`` for a URL ``client_id``, two branches:

    (a) fast path -- same scheme+host as the client_id; else
    (b) CIMD fetch -- exact-match against the metadata document's redirect_uris.
    """
    if _same_scheme_and_host(client_id, redirect_uri):
        return True
    try:
        registered = _fetch_cimd_redirect_uris(client_id)
    except Exception:
        return False
    return redirect_uri in registered


def _is_url_client_id(client_id: str) -> bool:
    parts = urlsplit(client_id or "")
    return parts.scheme in ("http", "https") and bool(parts.netloc)


# ---------------------------------------------------------------------------
# Validator: resolve/auto-provision a DOT Application for a URL client_id.
# ---------------------------------------------------------------------------
class MCPOAuth2Validator(OAuth2Validator):
    """Adds CIMD client resolution to DOT's validator.

    When ``client_id`` is a URL and no ``Application`` row exists yet, validate
    the requested ``redirect_uri`` (CIMD) and create a public, PKCE-only
    ``Application`` keyed on that URL. After that, DOT's stock flow (PKCE,
    grant, token) runs unchanged. We never expose a public registration
    endpoint -- provisioning only happens for a client_id that passes redirect
    validation during a real authorize request.
    """

    def _resolve_cimd_application(self, client_id, request):
        Application = get_application_model()
        try:
            return Application.objects.get(client_id=client_id)
        except Application.DoesNotExist:
            pass

        if not _is_url_client_id(client_id):
            return None

        redirect_uri = getattr(request, "redirect_uri", None)
        if not redirect_uri or not verify_redirect_uri(client_id, redirect_uri):
            return None

        # Auto-provision a public (no-secret), PKCE-enforced client. Store the
        # validated redirect_uri so DOT's own redirect check passes downstream.
        app, _created = Application.objects.get_or_create(
            client_id=client_id,
            defaults={
                "name": f"MCP client {urlsplit(client_id).netloc}",
                "client_type": Application.CLIENT_PUBLIC,
                "authorization_grant_type": Application.GRANT_AUTHORIZATION_CODE,
                "redirect_uris": redirect_uri,
                "client_secret": "",
                "skip_authorization": False,
                "user": None,
            },
        )
        # A returning client may use a second registered redirect_uri; append.
        if redirect_uri not in app.redirect_uris.split():
            app.redirect_uris = (app.redirect_uris + " " + redirect_uri).strip()
            app.save(update_fields=["redirect_uris"])
        return app

    def validate_client_id(self, client_id, request, *args, **kwargs):
        app = self._resolve_cimd_application(client_id, request)
        if app is not None:
            request.client = app
            return True
        return super().validate_client_id(client_id, request, *args, **kwargs)

    def authenticate_client_id(self, client_id, request, *args, **kwargs):
        # Token endpoint path for public clients (no Basic auth). Make sure the
        # CIMD-provisioned Application is loadable here too.
        self._resolve_cimd_application(client_id, request)
        return super().authenticate_client_id(client_id, request, *args, **kwargs)
