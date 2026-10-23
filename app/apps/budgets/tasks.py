"""Monthly auto-allocation for sinking-account categories.

For every TransactionCategory where:
  - account.kind == SINKING
  - monthly_default_amount is set and > 0
…this task creates a muted paired allocation:
  - EXPENSE on the owner's Main account (uncategorized)
  - INCOME on the sinking account (categorized to that sinking-account category)

Idempotent: identified by the description marker on the IN leg.
"""
from __future__ import annotations

import logging
from datetime import date

from django.db import transaction as db_transaction
from django.utils import timezone

from procrastinate.contrib.django import app

from apps.accounts.models import Account
from apps.budgets.models import Budget
from apps.common.middleware.thread_local import write_current_user
from apps.transactions.models import Transaction, TransactionCategory

logger = logging.getLogger(__name__)

_DESC_TEMPLATE = "[auto-allocation] {account} monthly allocation"


def _allocation_exists(category, month) -> bool:
    # userless manager: the idempotency check must not depend on whatever user
    # happens to be in thread-local storage when the task runs.
    return Transaction.userless_all_objects.filter(
        category=category,
        reference_date=month,
        type=Transaction.Type.INCOME,
        description=_DESC_TEMPLATE.format(account=category.account.name),
        deleted=False,
    ).exists()


def _main_account_for(owner) -> Account | None:
    owned = (
        Account.all_objects.filter(
            owner=owner, kind=Account.Kind.NORMAL, is_archived=False
        )
        .order_by("id")
        .first()
    )
    if owned is not None:
        return owned
    # Household setups: the category owner may not own a normal account
    # themselves — fall back to one shared with them (Account.objects is
    # visibility-scoped; write_current_user(owner) has already run).
    return (
        Account.objects.filter(kind=Account.Kind.NORMAL, is_archived=False)
        .order_by("id")
        .first()
    )


def materialize_for_month(month: date) -> int:
    """Create paired allocations for all sinking-account categories for `month`.
    Returns number of allocation pairs created."""
    month = month.replace(day=1)
    created = 0

    sinking_cats = TransactionCategory.all_objects.filter(
        account__kind=Account.Kind.SINKING,
        account__is_archived=False,
        monthly_default_amount__isnull=False,
        active=True,
    ).select_related("account", "owner")

    for cat in sinking_cats:
        amount = cat.monthly_default_amount
        if amount is None or amount <= 0:
            continue
        if _allocation_exists(cat, month):
            continue

        owner = cat.owner
        write_current_user(owner)
        main_acct = _main_account_for(owner)
        if main_acct is None:
            logger.warning("No Main account for owner=%s; skipping allocation %s", owner, cat)
            continue

        with db_transaction.atomic():
            Budget.all_objects.update_or_create(
                category=cat,
                month=month,
                defaults={"amount": amount, "owner": owner},
            )
            desc = _DESC_TEMPLATE.format(account=cat.account.name)
            Transaction.all_objects.create(
                account=main_acct,
                type=Transaction.Type.EXPENSE,
                date=month,
                reference_date=month,
                amount=amount,
                description=desc,
                category=None,
                is_paid=True,
                internal_note="Auto-generated monthly allocation (Main leg)",
                mute=True,
                owner=owner,
            )
            Transaction.all_objects.create(
                account=cat.account,
                type=Transaction.Type.INCOME,
                date=month,
                reference_date=month,
                amount=amount,
                description=desc,
                category=cat,
                is_paid=True,
                internal_note="Auto-generated monthly allocation",
                mute=True,
                owner=owner,
            )
            created += 1

    return created


@app.periodic(cron="5 0 1 * *")  # 00:05 on the 1st of each month
@app.task(lock="materialize_monthly_allocations", name="materialize_monthly_allocations")
def materialize_monthly_allocations(timestamp=None):
    try:
        today = timezone.localdate(timezone.now())
        n = materialize_for_month(today)
        return f"Created {n} allocation pairs for {today.year}-{today.month:02d}"
    except Exception:
        logger.exception("Error in materialize_monthly_allocations")
        raise
