"""Budget analysis: current-month KPIs, a multi-month budget-vs-spent trend for
normal categories, and a running-balance series per sinking fund.

Current-month normal numbers reuse ``monthly_status`` so they agree exactly with
the Budget tab on the monthly overview. The trend and fund series use efficient
aggregate queries, all keyed on ``reference_date`` for self-consistency.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Case, DecimalField, F, Sum, When
from django.db.models.functions import TruncMonth

from apps.accounts.models import Account
from apps.budgets.models import Budget
from apps.budgets.services.monthly import monthly_status
from apps.transactions.models import Transaction, TransactionCategory


def _signed_amount_expr():
    return Case(
        When(type=Transaction.Type.INCOME, then=F("amount")),
        default=-F("amount"),
        output_field=DecimalField(max_digits=42, decimal_places=30),
    )


def _month_list(end: date, months: int) -> list[date]:
    start = end - relativedelta(months=months - 1)
    out, m = [], start
    while m <= end:
        out.append(m)
        m += relativedelta(months=1)
    return out


def _label(m: date) -> str:
    return m.strftime("%b %Y")


def budget_analysis(user, year: int, month: int, months: int = 12) -> dict:
    """Scoping happens through the sharing-aware default managers (thread-local
    user); ``user`` is kept for interface clarity only."""
    current = date(year, month, 1)
    window = _month_list(current, months)
    window_start = window[0]

    # --- Current month: normal-category budget levels + KPIs (reuse monthly_status) ---
    rows = monthly_status(user, year, month)
    normal_rows = [
        r for r in rows if r.account and r.account.kind == Account.Kind.NORMAL
    ]

    levels = []
    total_budget = total_spent = Decimal(0)
    over_count = 0
    for r in normal_rows:
        budget = r.budget or Decimal(0)
        spent = r.spent or Decimal(0)
        if budget == 0 and spent == 0:
            continue
        total_budget += budget
        total_spent += spent
        over = budget > 0 and spent > budget
        over_count += 1 if over else 0
        pct = float(spent / budget * 100) if budget > 0 else None
        levels.append(
            {
                "id": r.category.id,
                "name": r.category.name,
                "budget": budget,
                "spent": spent,
                "remaining": budget - spent,
                "pct": pct,
                "bar": min(pct, 100) if pct is not None else 0,  # clamped for <progress>
                "over": over,
                "has_budget": budget > 0,
            }
        )
    # most-stressed first; unbudgeted-but-spent categories sink to the bottom
    levels.sort(key=lambda x: (x["pct"] is None, -(x["pct"] or 0)))

    kpi = {
        "budget": total_budget,
        "spent": total_spent,
        "remaining": total_budget - total_spent,
        "pct": float(total_spent / total_budget * 100) if total_budget > 0 else None,
        "over_count": over_count,
        "count": len(levels),
    }

    # --- Trend: per-category (and total) budget vs spent over the window ---
    norm_cats = list(
        TransactionCategory.objects.filter(
            active=True, account__kind=Account.Kind.NORMAL
        )
        .order_by("name")
        .values("id", "name", "monthly_default_amount")
    )
    norm_ids = [c["id"] for c in norm_cats]

    spent_cm: dict[tuple[int, date], Decimal] = {}
    for r in (
        Transaction.objects.filter(
            type=Transaction.Type.EXPENSE,
            category_id__in=norm_ids,
            reference_date__gte=window_start,
            reference_date__lte=current,
        )
        .annotate(m=TruncMonth("reference_date"))
        .values("category_id", "m")
        .annotate(total=Sum("amount"))
    ):
        spent_cm[(r["category_id"], r["m"])] = r["total"] or Decimal(0)

    # explicit Budget rows override the per-category default for their month
    explicit: dict[date, dict[int, Decimal]] = {}
    for b in Budget.all_objects.filter(
        category_id__in=norm_ids,
        month__gte=window_start,
        month__lte=current,
    ).values("category_id", "month", "amount"):
        explicit.setdefault(b["month"], {})[b["category_id"]] = b["amount"]

    labels = [_label(m) for m in window]
    all_budget = [Decimal(0)] * len(window)
    all_spent = [Decimal(0)] * len(window)
    cat_series = []
    for c in norm_cats:
        cid, default = c["id"], (c["monthly_default_amount"] or Decimal(0))
        b_arr, s_arr = [], []
        for i, m in enumerate(window):
            b = explicit.get(m, {}).get(cid, default) or Decimal(0)
            s = spent_cm.get((cid, m), Decimal(0))
            b_arr.append(float(b))
            s_arr.append(float(s))
            all_budget[i] += b
            all_spent[i] += s
        if any(b_arr) or any(s_arr):
            cat_series.append(
                {"id": cid, "name": c["name"], "budget": b_arr, "spent": s_arr}
            )

    trend = {
        "labels": labels,
        "all": {
            "budget": [float(x) for x in all_budget],
            "spent": [float(x) for x in all_spent],
        },
        "categories": cat_series,
    }

    # --- Sinking funds: running balance per account over the window ---
    opening = dict(
        Transaction.objects.filter(
            account__kind=Account.Kind.SINKING,
            reference_date__lt=window_start,
        )
        .values_list("account_id")
        .annotate(t=Sum(_signed_amount_expr()))
        .values_list("account_id", "t")
    )
    deltas: dict[tuple[int, date], Decimal] = {}
    for r in (
        Transaction.objects.filter(
            account__kind=Account.Kind.SINKING,
            reference_date__gte=window_start,
            reference_date__lte=current,
        )
        .annotate(m=TruncMonth("reference_date"))
        .values("account_id", "m")
        .annotate(t=Sum(_signed_amount_expr()))
    ):
        deltas[(r["account_id"], r["m"])] = r["t"] or Decimal(0)

    acct_ids = set(opening) | {aid for (aid, _m) in deltas}
    acct_names = dict(
        Account.all_objects.filter(id__in=acct_ids).values_list("id", "name")
    )

    sinking = {"labels": [_label(m) for m in window], "series": [], "current": []}
    for aid in sorted(acct_ids, key=lambda a: acct_names.get(a, "")):
        running = opening.get(aid, Decimal(0))
        data = []
        for m in window:
            running += deltas.get((aid, m), Decimal(0))
            data.append(float(running))
        name = acct_names.get(aid, "?")
        sinking["series"].append({"name": name, "data": data})
        sinking["current"].append({"name": name, "balance": float(running)})

    sinking["total"] = sum(f["balance"] for f in sinking["current"])

    return {"levels": levels, "kpi": kpi, "trend": trend, "sinking": sinking}
