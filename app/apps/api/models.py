import binascii
import os

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class APIToken(models.Model):
    """A per-user, named, scoped API token.

    DRF's built-in authtoken is one-per-user and unscoped; this model allows
    multiple named tokens per user, each carrying a read-only / read-write
    scope enforced by ``apps.api.permissions.TokenScopePermission``.
    """

    class Scope(models.TextChoices):
        READ_ONLY = "read_only", _("Read only")
        READ_WRITE = "read_write", _("Read and write")

    key = models.CharField(_("Key"), max_length=40, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_tokens",
        verbose_name=_("User"),
    )
    name = models.CharField(_("Name"), max_length=255)
    scope = models.CharField(
        _("Scope"),
        max_length=16,
        choices=Scope.choices,
        default=Scope.READ_ONLY,
    )
    created_at = models.DateTimeField(_("Created"), auto_now_add=True)
    last_used_at = models.DateTimeField(_("Last used"), null=True, blank=True)

    class Meta:
        verbose_name = _("API token")
        verbose_name_plural = _("API tokens")
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super().save(*args, **kwargs)

    @classmethod
    def generate_key(cls):
        # Mirrors rest_framework.authtoken.models.Token.generate_key.
        return binascii.hexlify(os.urandom(20)).decode()

    @property
    def is_read_only(self):
        return self.scope == self.Scope.READ_ONLY

    def __str__(self):
        return f"{self.name} ({self.get_scope_display()})"
