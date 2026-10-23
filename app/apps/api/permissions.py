from rest_framework.permissions import SAFE_METHODS, BasePermission
from django.conf import settings

from apps.api.models import APIToken


class NotInDemoMode(BasePermission):
    def has_permission(self, request, view):
        if settings.DEMO and not request.user.is_superuser:
            return False
        else:
            return True


class TokenScopePermission(BasePermission):
    """Enforces the scope of a scoped ``APIToken``.

    Only applies when the request was authenticated with one of our
    ``APIToken``s (``request.auth`` is an ``APIToken`` instance). For any
    other auth (session, basic, built-in authtoken) it returns ``True`` and
    has no effect, so the web UI stays fully functional. A ``read_only``
    token may only use SAFE methods; anything else is denied.
    """

    message = "This API token is read-only."

    def has_permission(self, request, view):
        token = getattr(request, "auth", None)
        if not isinstance(token, APIToken):
            return True
        if token.is_read_only and request.method not in SAFE_METHODS:
            return False
        return True
