from django.utils import timezone
from rest_framework.authentication import TokenAuthentication

from apps.api.models import APIToken


class APITokenAuthentication(TokenAuthentication):
    """Authenticates scoped ``APIToken``s via ``Authorization: Token <key>``.

    Shares the ``Token`` keyword with DRF's built-in ``TokenAuthentication``,
    so this class MUST be listed *before* it in
    ``DEFAULT_AUTHENTICATION_CLASSES``. On a key miss we return ``None``
    instead of raising, so a key that belongs to the built-in authtoken table
    can still fall through and be authenticated by the built-in class (a
    genuinely invalid key is rejected downstream). ``request.auth`` is set to
    the ``APIToken`` instance so scope is available to the permission layer.
    """

    model = APIToken

    def authenticate_credentials(self, key):
        try:
            token = APIToken.objects.select_related("user").get(key=key)
        except APIToken.DoesNotExist:
            return None

        if not token.user.is_active:
            from rest_framework import exceptions

            raise exceptions.AuthenticationFailed("User inactive or deleted.")

        # Throttle DB writes; only persist when the value actually changes.
        now = timezone.now()
        if token.last_used_at is None or (now - token.last_used_at).total_seconds() > 60:
            token.last_used_at = now
            token.save(update_fields=["last_used_at"])

        return (token.user, token)
