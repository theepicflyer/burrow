from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.common.middleware.thread_local import get_current_user
from apps.common.models import OwnedObject, in_household
from apps.transactions.validators import validate_decimal_places, validate_non_negative


class BudgetManager(models.Manager):
    """Visibility follows the budget's category (a SharedObject), not the row's
    owner — a budget is a fact about the category, so anyone the category is
    shared with sees the same numbers."""

    def get_queryset(self):
        user = get_current_user()
        qs = super().get_queryset()
        if in_household(user):
            return qs
        if user and user.is_authenticated:
            return qs.filter(
                Q(category__visibility="public")
                | Q(category__owner=user)
                | Q(category__shared_with=user)
                | Q(category__visibility="private", category__owner=None)
            ).distinct()
        return qs.none()


class Budget(OwnedObject):
    """One row per (category, month). For sinking-account categories this is
    the monthly auto-allocation override; for normal-account categories it's
    the planned budget for that category.
    """

    category = models.ForeignKey(
        "transactions.TransactionCategory",
        on_delete=models.CASCADE,
        related_name="budgets",
        verbose_name=_("Category"),
    )
    month = models.DateField(verbose_name=_("Month"))  # always day=1
    amount = models.DecimalField(
        max_digits=42,
        decimal_places=30,
        verbose_name=_("Amount"),
        validators=[validate_non_negative, validate_decimal_places],
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    all_objects = models.Manager()  # unfiltered; keep declared FIRST so it
    # stays the default manager (reverse relations / services rely on it).
    objects = BudgetManager()  # category-visibility filtered; used by the API

    class Meta:
        verbose_name = _("Budget")
        verbose_name_plural = _("Budgets")
        db_table = "budgets"
        unique_together = (("category", "month"),)
        ordering = ["-month", "category_id"]

    def save(self, *args, **kwargs):
        if self.month:
            self.month = self.month.replace(day=1)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.category} {self.month:%Y-%m}: {self.amount}"
