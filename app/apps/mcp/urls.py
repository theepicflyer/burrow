"""MCP endpoint mount + OAuth discovery/endpoints.

Kept in this app (not WYGIWYH/urls.py) so all the MCP + OAuth wiring lives in
one auditable place. The project urlconf only ``include()``s this module.

Auth on ``/mcp``: the configured ``DJANGO_MCP_AUTHENTICATION_CLASSES`` (API
token + OAuth Bearer + session). An unauthenticated request returns ``401``
with a ``WWW-Authenticate: Bearer resource_metadata="..."`` challenge (see
``_MCPView.get_authenticate_header``) that kicks off the claude.ai discovery
handshake. Per-tool read/write scope is enforced downstream on the DRF
ViewSets (``TokenScopePermission`` for API tokens, ``OAuthScopePermission``
for OAuth tokens).

The OAuth ``authorize``/``token`` endpoints come from django-oauth-toolkit
(mounted under ``/oauth/``); the discovery ``.well-known`` documents and the
CIMD client resolution are hand-built in ``apps.mcp.oauth``.
"""

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.utils.module_loading import import_string
from django.conf import settings
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import IsAuthenticated

from oauth2_provider import views as oauth2_views

from apps.api.permissions import NotInDemoMode
from apps.mcp import oauth
from mcp_server.views import MCPServerStreamableHttpView

_auth_classes = [
    import_string(cls)
    for cls in getattr(settings, "DJANGO_MCP_AUTHENTICATION_CLASSES", [])
]


class _MCPView(MCPServerStreamableHttpView):
    """MCP endpoint that emits the RFC 9728 Bearer challenge on 401."""

    def get_authenticate_header(self, request):
        return oauth.www_authenticate_value(request)


class _AuthorizationView(oauth2_views.AuthorizationView):
    """Authorize endpoint with RFC 8707 audience (``resource``) validation."""

    def dispatch(self, request, *args, **kwargs):
        if not oauth.resource_param_ok(request):
            return JsonResponse(
                {"error": "invalid_target"}, status=400
            )
        return super().dispatch(request, *args, **kwargs)


@method_decorator(csrf_exempt, name="dispatch")
class _TokenView(oauth2_views.TokenView):
    """Token endpoint with RFC 8707 audience (``resource``) validation.

    ``csrf_exempt`` must be re-applied: DOT decorates ``TokenView.dispatch``,
    but overriding ``dispatch`` here defines a fresh, non-exempt method (public
    clients post to /oauth/token with no CSRF cookie)."""

    def dispatch(self, request, *args, **kwargs):
        if not oauth.resource_param_ok(request):
            return JsonResponse(
                {"error": "invalid_target"}, status=400
            )
        return super().dispatch(request, *args, **kwargs)


urlpatterns = [
    path(
        "mcp",
        _MCPView.as_view(
            authentication_classes=_auth_classes,
            permission_classes=[NotInDemoMode, IsAuthenticated],
        ),
        name="mcp_server_streamable_http_endpoint",
    ),
    # RFC 9728 protected-resource metadata. claude.ai probes the path-suffixed
    # variant first, so serve both. No auth (public by spec).
    path(
        ".well-known/oauth-protected-resource",
        oauth.protected_resource_metadata,
        name="oauth_protected_resource_metadata",
    ),
    path(
        ".well-known/oauth-protected-resource/mcp",
        oauth.protected_resource_metadata,
        name="oauth_protected_resource_metadata_mcp",
    ),
    # RFC 8414 authorization-server metadata. No auth (public by spec).
    path(
        ".well-known/oauth-authorization-server",
        oauth.authorization_server_metadata,
        name="oauth_authorization_server_metadata",
    ),
    # django-oauth-toolkit's authorize/token endpoints (PKCE, grant, token).
    # Only these two are mounted -- NOT DOT's application-management UI or its
    # OIDC discovery -- to keep the public OAuth surface minimal. The
    # ``oauth2_provider`` namespace is what reverse() targets in apps.mcp.oauth.
    path(
        "oauth/",
        include(
            (
                [
                    path(
                        "authorize/",
                        _AuthorizationView.as_view(),
                        name="authorize",
                    ),
                    path(
                        "token/",
                        _TokenView.as_view(),
                        name="token",
                    ),
                ],
                "oauth2_provider",
            ),
            namespace="oauth2_provider",
        ),
    ),
]
