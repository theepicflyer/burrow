"""Monthly budget-vs-actual status per category."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Case, DecimalField, F, Sum, When

from apps.accounts.models import Account
from apps.budgets.models import Budget
from apps.transactions.models import Transaction, TransactionCategory


@dataclass
class CategoryStatus:
    category: TransactionCategory
    account: Account | None
    budget: Decimal | None
    spent: Decimal
    received: Decimal
    carryover: Decimal | None  # only meaningful for sinking-account categories

    @property
    def balance(self) -> Decimal | None:
        if self.carryover is None:
            return None
        return self.carryover + self.received - self.spent


def _signed_amount_expr():
    return Case(
        When(type=Transaction.Type.INCOME, then=F("amount")),
        default=-F("amount"),
        output_field=DecimalField(max_digits=42, decimal_places=30),
    )


def _budget_for(category, month: date) -> Decimal | None:
    explicit = (
        Budget.all_objects.filter(category=category, month=month)
        .values_list("amount", flat=True)
        .first()
    )
    if explicit is not None:
        return explicit
    return category.monthly_default_amount


def monthly_status(user, year: int, month: int) -> list[CategoryStatus]:
    """Rows for every category visible to the requesting user. Scoping happens
    through the sharing-aware default managers (thread-local user), so all
    household members see identical numbers for shared categories/accounts;
    ``user`` is kept for interface clarity only."""
    month_d = date(year, month, 1)

    cats = (
        TransactionCategory.objects.filter(active=True)
        .select_related("account")
        .order_by("account__kind", "account__name", "name")
    )

    txns_this_month = Transaction.objects.filter(
        reference_date__year=year,
        reference_date__month=month,
    )
    spent_by_cat = dict(
        txns_this_month.filter(type=Transaction.Type.EXPENSE)
        .values_list("category_id")
        .annotate(total=Sum("amount"))
        .values_list("category_id", "total")
    )
    received_by_cat = dict(
        txns_this_month.filter(type=Transaction.Type.INCOME)
        .values_list("category_id")
        .annotate(total=Sum("amount"))
        .values_list("category_id", "total")
    )

    carryover_by_cat = dict(
        Transaction.objects.filter(date__lt=month_d)
        .values_list("category_id")
        .annotate(total=Sum(_signed_amount_expr()))
        .values_list("category_id", "total")
    )

    rows: list[CategoryStatus] = []
    for cat in cats:
        is_sinking = cat.account and cat.account.kind == Account.Kind.SINKING
        rows.append(
            CategoryStatus(
                category=cat,
                account=cat.account,
                budget=_budget_for(cat, month_d),
                spent=spent_by_cat.get(cat.id, Decimal(0)) or Decimal(0),
                received=received_by_cat.get(cat.id, Decimal(0)) or Decimal(0),
                carryover=(carryover_by_cat.get(cat.id, Decimal(0)) or Decimal(0))
                if is_sinking
                else None,
            )
        )
    return rows
