from datetime import date
from decimal import Decimal, InvalidOperation

from dateutil.relativedelta import relativedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.accounts.models import Account
from apps.budgets.models import Budget
from apps.budgets.services.analysis import budget_analysis
from apps.budgets.services.monthly import monthly_status
from apps.common.decorators.htmx import only_htmx
from apps.transactions.models import Transaction, TransactionCategory


def _current_month_first() -> date:
    today = timezone.localdate(timezone.now())
    return date(today.year, today.month, 1)


def _earliest_txn_month() -> date | None:
    # Transaction.objects is account-visibility scoped (thread-local user), so
    # both household members backfill against the same ledger history.
    earliest = (
        Transaction.objects.order_by("reference_date")
        .values_list("reference_date", flat=True)
        .first()
    )
    if earliest is None:
        return None
    return date(earliest.year, earliest.month, 1)


@login_required
@require_http_methods(["GET", "POST"])
def budgets_edit(request):
    current_month = _current_month_first()

    cats = list(
        TransactionCategory.objects.filter(active=True)
        .select_related("account")
        .order_by("account__kind", "account__name", "name")
    )

    if request.method == "POST":
        errors = []
        parsed: list[tuple[TransactionCategory, Decimal | None]] = []
        for cat in cats:
            raw = (request.POST.get(f"amount_{cat.id}") or "").strip()
            if raw == "":
                parsed.append((cat, None))
                continue
            try:
                val = Decimal(raw)
            except (InvalidOperation, ValueError):
                errors.append(_("Invalid amount for %(name)s") % {"name": cat.name})
                continue
            if val < 0:
                errors.append(_("Amount must be non-negative for %(name)s") % {"name": cat.name})
                continue
            parsed.append((cat, val))

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            earliest = _earliest_txn_month()
            changed = 0
            with db_transaction.atomic():
                for cat, new_val in parsed:
                    old_val = cat.monthly_default_amount
                    if old_val == new_val:
                        continue

                    if old_val is not None and earliest is not None:
                        m = earliest
                        while m < current_month:
                            Budget.all_objects.get_or_create(
                                category=cat,
                                month=m,
                                defaults={"amount": old_val, "owner": request.user},
                            )
                            m = m + relativedelta(months=1)

                    if new_val is None:
                        Budget.all_objects.filter(category=cat, month=current_month).delete()
                    else:
                        Budget.all_objects.update_or_create(
                            category=cat,
                            month=current_month,
                            defaults={"amount": new_val, "owner": request.user},
                        )

                    cat.monthly_default_amount = new_val
                    cat.save(update_fields=["monthly_default_amount"])
                    changed += 1

            if changed:
                messages.success(
                    request,
                    _("Updated %(n)d budget(s).") % {"n": changed},
                )
            return redirect("budgets_edit")

    normal_cats = [
        c for c in cats
        if c.account and c.account.kind == Account.Kind.NORMAL
    ]
    sinking_cats = [
        c for c in cats
        if c.account and c.account.kind == Account.Kind.SINKING
    ]

    return render(
        request,
        "budgets/pages/budgets_edit.html",
        {
            "normal_cats": normal_cats,
            "sinking_cats": sinking_cats,
            "current_month": current_month,
        },
    )


@login_required
@require_http_methods(["GET"])
def budgets_analysis(request, year: int | None = None, month: int | None = None):
    if year is None or month is None:
        cm = _current_month_first()
        year, month = cm.year, cm.month

    selected = date(year, month, 1)
    prev_m = selected - relativedelta(months=1)
    next_m = selected + relativedelta(months=1)

    multi_currency = (
        Transaction.objects.values("account__currency_id")
        .distinct()
        .count()
        > 1
    )

    data = budget_analysis(request.user, year, month)
    # Stash art: 15 acorns for the fullest fund, the rest in proportion (funds have no target).
    peak = max((f["balance"] for f in data["sinking"]["current"]), default=0)
    for f in data["sinking"]["current"]:
        f["acorns"] = round(f["balance"] / peak * 15) if peak > 0 else 0

    return render(
        request,
        "budgets/pages/analysis.html",
        {
            "data": data,
            "year": year,
            "month": month,
            "prev_year": prev_m.year,
            "prev_month": prev_m.month,
            "next_year": next_m.year,
            "next_month": next_m.month,
            "multi_currency": multi_currency,
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def budget_category_transactions(request, category_id: int, year: int, month: int):
    """Offcanvas preview of one category's transactions for the selected month.
    Filtered identically to monthly_status' `spent` (reference_date, Transaction.objects)
    so the EXPENSE total reconciles with the category's budget-level bar."""
    category = get_object_or_404(TransactionCategory.objects, id=category_id)
    transactions = (
        Transaction.objects.filter(
            category_id=category_id,
            reference_date__year=year,
            reference_date__month=month,
        )
        .select_related(
            "account__currency",
            "account__group",
            "category",
            "installment_plan",
            "recurring_transaction",
        )
        .prefetch_related("entities", "tags", "dca_expense_entries", "dca_income_entries")
        .order_by("-date", "-id")
    )
    spent = sum(
        (t.amount for t in transactions if t.type == Transaction.Type.EXPENSE), Decimal(0)
    )
    received = sum(
        (t.amount for t in transactions if t.type == Transaction.Type.INCOME), Decimal(0)
    )

    return render(
        request,
        "budgets/fragments/category_transactions.html",
        {
            "category": category,
            "transactions": transactions,
            "spent": spent,
            "received": received,
            "year": year,
            "month": month,
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def monthly_budget_status(request, month: int, year: int):
    rows = monthly_status(request.user, year, month)
    normal_rows = [r for r in rows if r.account and r.account.kind == Account.Kind.NORMAL]
    sinking_rows = [r for r in rows if r.account and r.account.kind == Account.Kind.SINKING]

    def _totals(group_rows, budget_attr):
        spent = sum((r.spent or Decimal(0) for r in group_rows), Decimal(0))
        budget = sum(
            (getattr(r, budget_attr) or Decimal(0) for r in group_rows), Decimal(0)
        )
        return {"spent": spent, "budget": budget}

    normal_totals = _totals(normal_rows, "budget")
    sinking_totals = _totals(sinking_rows, "received")
    grand_totals = {
        "spent": normal_totals["spent"] + sinking_totals["spent"],
        "budget": normal_totals["budget"] + sinking_totals["budget"],
    }
    grand_totals["balance"] = grand_totals["budget"] - grand_totals["spent"]

    return render(
        request,
        "budgets/fragments/monthly_budget_status.html",
        {
            "normal_rows": normal_rows,
            "sinking_rows": sinking_rows,
            "normal_totals": normal_totals,
            "sinking_totals": sinking_totals,
            "grand_totals": grand_totals,
            "month": month,
            "year": year,
        },
    )
