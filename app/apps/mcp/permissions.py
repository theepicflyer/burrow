"""OAuth read/write scope enforcement for the MCP / API surface.

``apps.api.permissions.TokenScopePermission`` only knows about our own
``APIToken``s; it does nothing for an OAuth Bearer token. This permission is
its OAuth counterpart: it maps ``mcp:read`` to SAFE (read) HTTP methods and
``mcp:write`` to unsafe (write) methods, and denies a token that lacks the
scope its method needs.

CRITICAL no-op contract: DRF AND-s all default permission classes together, so
this class MUST return ``True`` for any request that is NOT authenticated by an
OAuth ``AccessToken`` -- exactly as ``TokenScopePermission`` no-ops for
non-``APIToken`` auth. Otherwise a request carrying an ``APIToken`` (which has
no OAuth scope) would be denied every write tool, silently breaking the CLI
path. We detect an OAuth token by the ``AccessToken``/``allow_scopes`` shape so
the check never fires for sessions, ``APIToken``s, or built-in authtokens.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from oauth2_provider.models import get_access_token_model


class OAuthScopePermission(BasePermission):
    message = "This OAuth token does not have the required scope."

    def has_permission(self, request, view):
        token = getattr(request, "auth", None)
        # No-op for everything that is not an OAuth AccessToken (sessions,
        # APITokens, built-in authtokens). See module docstring.
        if not isinstance(token, get_access_token_model()):
            return True
        required = "mcp:read" if request.method in SAFE_METHODS else "mcp:write"
        return token.allow_scopes([required])
