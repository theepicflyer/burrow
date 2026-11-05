"""Burrow's household ledger.

One shared ledger: every signed-in user sees and edits everything. There are no
accounts or wallet balances; the ledger is a list of spends, each in a category.

* A ``Category`` is either a **budget** (normal spending with a monthly budget)
  or a **fund** (a sinking fund that grows by a monthly top-up on the 1st and
  shrinks by whatever is spent from it).
* The monthly amount (budget or top-up) is effective-dated in ``MonthlyAmount``:
  the amount for month M is the latest row starting on or before M. Changing it
  adds a row from that month on, so past months keep the amount they had.
* A ``Transaction`` has a ``date`` (when it happened or was billed) and a
  ``month`` it counts toward, which defaults to the date's month but can differ
  (May's transport bill arrives on 10 June and counts toward May).
* A ``Recurring`` rule creates transactions as they fall due. Nothing is created
  ahead of time, so editing a rule changes every entry it has yet to create.
"""

from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.ledger.months import add_months, month_of

MONEY = {"max_digits": 14, "decimal_places": 2}


class LedgerSettings(models.Model):
    """Household-wide settings. A single row, loaded with ``LedgerSettings.load()``."""

    currency = models.CharField(
        _("Currency symbol"), max_length=8, default="$", help_text=_("Shown before amounts, e.g. S$")
    )

    class Meta:
        verbose_name = _("Ledger settings")
        verbose_name_plural = _("Ledger settings")

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Ledger settings"


class Category(models.Model):
    class Kind(models.TextChoices):
        BUDGET = "budget", _("Budget")
        FUND = "fund", _("Fund")

    name = models.CharField(_("Name"), max_length=80, unique=True)
    kind = models.CharField(_("Kind"), max_length=8, choices=Kind.choices, default=Kind.BUDGET)
    position = models.PositiveIntegerField(_("Position"), default=0)
    archived = models.BooleanField(_("Archived"), default=False)
    opening_balance = models.DecimalField(
        _("Opening balance"),
        default=Decimal("0"),
        help_text=_("Funds only: the balance before the first top-up."),
        **MONEY,
    )
    target = models.DecimalField(
        _("Target"),
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text=_("Funds only: what the fund is saving up to. Optional."),
        **MONEY,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")
        ordering = ["kind", "position", "name"]

    def __str__(self):
        return self.name

    @property
    def is_fund(self):
        return self.kind == self.Kind.FUND

    def amount_for(self, month: date) -> Decimal:
        """Budget (or fund top-up) for ``month``; 0 before the first amount."""
        row = (
            self.amounts.filter(start_month__lte=month_of(month))
            .order_by("-start_month")
            .values_list("amount", flat=True)
            .first()
        )
        return row if row is not None else Decimal("0")

    def set_amount(self, amount: Decimal, from_month: date) -> "MonthlyAmount":
        """Set the monthly amount from ``from_month`` on. Earlier months keep theirs;
        later rows that already exist are left alone (they were set on purpose)."""
        obj, _created = MonthlyAmount.objects.update_or_create(
            category=self, start_month=month_of(from_month), defaults={"amount": amount}
        )
        return obj

    @property
    def first_month(self) -> date | None:
        return self.amounts.order_by("start_month").values_list("start_month", flat=True).first()


class MonthlyAmount(models.Model):
    """The category's monthly budget (or fund top-up) from ``start_month`` until
    the next row."""

    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="amounts")
    start_month = models.DateField(_("From month"))
    amount = models.DecimalField(_("Amount"), validators=[MinValueValidator(0)], **MONEY)

    class Meta:
        verbose_name = _("Monthly amount")
        verbose_name_plural = _("Monthly amounts")
        ordering = ["category", "start_month"]
        constraints = [
            models.UniqueConstraint(fields=["category", "start_month"], name="ledger_amount_unique_month")
        ]

    def save(self, *args, **kwargs):
        self.start_month = month_of(self.start_month)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.category} from {self.start_month:%Y-%m}: {self.amount}"


class Transaction(models.Model):
    """A spend. A negative amount is money back (a refund, or money put into a fund)."""

    amount = models.DecimalField(_("Amount"), **MONEY)
    title = models.CharField(_("Title"), max_length=200)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="transactions", verbose_name=_("Category")
    )
    date = models.DateField(_("Date"), default=timezone.localdate)
    month = models.DateField(_("Counts toward"), help_text=_("The month this counts toward."))
    note = models.TextField(_("Note"), blank=True)
    recurring = models.ForeignKey(
        "Recurring", on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Transaction")
        verbose_name_plural = _("Transactions")
        ordering = ["-date", "-created_at", "-id"]
        indexes = [
            models.Index(fields=["month", "category"]),
            models.Index(fields=["-date", "-created_at"]),
        ]

    def save(self, *args, **kwargs):
        self.month = month_of(self.month or self.date)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} {self.title} {self.amount}"

    @property
    def counts_elsewhere(self) -> bool:
        return self.month != month_of(self.date)

    def as_entry(self) -> dict:
        """What the add/edit sheet needs to open this spend."""
        return {
            "id": self.id,
            "amount": str(abs(self.amount)),
            "refund": self.amount < 0,
            "title": self.title,
            "category": self.category_id,
            "date": self.date.isoformat(),
            "month": self.month.strftime("%Y-%m"),
            "note": self.note,
            "recurring": self.recurring_id,
            "recurring_title": self.recurring.title if self.recurring_id else "",
        }


class Recurring(models.Model):
    class Unit(models.TextChoices):
        WEEK = "week", _("Week")
        MONTH = "month", _("Month")
        YEAR = "year", _("Year")

    title = models.CharField(_("Title"), max_length=200)
    amount = models.DecimalField(_("Amount"), **MONEY)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="recurring", verbose_name=_("Category")
    )
    note = models.TextField(_("Note"), blank=True)
    every = models.PositiveSmallIntegerField(_("Every"), default=1, validators=[MinValueValidator(1)])
    unit = models.CharField(_("Unit"), max_length=8, choices=Unit.choices, default=Unit.MONTH)
    start_date = models.DateField(_("First date"))
    end_date = models.DateField(_("Last date"), null=True, blank=True)
    month_offset = models.SmallIntegerField(
        _("Counts toward"),
        default=0,
        choices=[(0, _("Same month")), (-1, _("Previous month"))],
    )
    paused = models.BooleanField(_("Paused"), default=False)
    last_generated = models.DateField(
        null=True, blank=True, help_text=_("Date of the last entry this rule created.")
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Recurring spend")
        verbose_name_plural = _("Recurring spends")
        ordering = ["title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # ``last_generated`` is owned by ``services.generate_due``. A plain save of a
        # rule loaded earlier must not write back a stale value (that would make the
        # rule create the same entries again), so it is only written when named.
        if not self._state.adding and kwargs.get("update_fields") is None:
            kwargs["update_fields"] = [
                f.name for f in self._meta.concrete_fields if not f.primary_key and f.name != "last_generated"
            ]
        super().save(*args, **kwargs)

    def occurrence(self, n: int) -> date:
        """The n-th date of the schedule (0 = start). Computed from the start each
        time so the 31st stays the 31st (or the month's last day), never drifting."""
        k = n * self.every
        if self.unit == self.Unit.WEEK:
            return self.start_date + timedelta(weeks=k)
        if self.unit == self.Unit.YEAR:
            return self.start_date + relativedelta(years=k)
        return self.start_date + relativedelta(months=k)

    def dates_between(self, after: date | None, until: date) -> list[date]:
        """Schedule dates in ``(after, until]``, bounded by ``end_date``."""
        out, n = [], 0
        if self.end_date:
            until = min(until, self.end_date)
        while True:
            d = self.occurrence(n)
            if d > until:
                return out
            if after is None or d > after:
                out.append(d)
            n += 1

    def next_date(self) -> date | None:
        """The next date this rule will create an entry on, or ``None`` if it has ended."""
        after = self.last_generated or (self.start_date - timedelta(days=1))
        n = 0
        while True:
            d = self.occurrence(n)
            if self.end_date and d > self.end_date:
                return None
            if d > after:
                return d
            n += 1

    def month_for(self, d: date) -> date:
        return add_months(month_of(d), self.month_offset)

    @property
    def frequency_label(self) -> str:
        unit = self.get_unit_display().lower()
        if self.every == 1:
            return {"week": _("Weekly"), "month": _("Monthly"), "year": _("Yearly")}[self.unit]
        return _("Every %(n)s %(unit)ss") % {"n": self.every, "unit": unit}
