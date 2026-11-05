from datetime import timedelta
from decimal import Decimal
from itertools import groupby

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.api.models import APIToken
from apps.ledger import services
from apps.ledger.forms import CategoryForm, LedgerSettingsForm, RecurringForm, SpendForm
from apps.ledger.models import Category, LedgerSettings, MonthlyAmount, Recurring, Transaction
from apps.ledger.months import add_months, month_of, parse_month
from apps.ledger.templatetags.ledger import format_money


def _today():
    return timezone.localdate()


# --------------------------------------------------------------------------- pages


@login_required
def home(request):
    services.generate_due()
    today = _today()
    month = parse_month(request.GET.get("month"), today)
    status = services.month_status(month, today=today)
    recent = Transaction.objects.select_related("category").filter(month=month)[:6]
    upcoming = []
    if month == month_of(today):
        upcoming = services.upcoming(today + timedelta(days=14), today=today)[:5]
    return render(
        request,
        "ledger/home.html",
        {
            "status": status,
            "month": month,
            "prev_month": add_months(month, -1),
            "next_month": add_months(month, 1),
            "is_current": month == month_of(today),
            "recent": recent,
            "upcoming": upcoming,
            "nav": "home",
        },
    )


def _spend_filters(request):
    q = request.GET.get("q", "").strip()
    month = request.GET.get("month", "")
    category = request.GET.get("category", "")
    qs = Transaction.objects.select_related("category", "recurring", "created_by")
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(note__icontains=q))
    if month:
        qs = qs.filter(month=parse_month(month, _today()))
    if category.isdigit():
        qs = qs.filter(category_id=int(category))
    return qs, {"q": q, "month": month, "category": category}


@login_required
def spends(request):
    services.generate_due()
    qs, filters = _spend_filters(request)
    page = Paginator(qs, 60).get_page(request.GET.get("page"))
    days = [(d, list(rows)) for d, rows in groupby(page.object_list, key=lambda t: t.date)]
    total = qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    ctx = {
        "page": page,
        "days": days,
        "filters": filters,
        "total": total,
        "count": page.paginator.count,
        "filtered": any(filters.values()),
        "categories": Category.objects.all(),
        "months": [add_months(month_of(_today()), -i) for i in range(-1, 24)],
        "today": _today(),
        "this_year": _today().year,
        "nav": "spends",
    }
    if request.headers.get("HX-Request") and request.GET.get("page"):
        return render(request, "ledger/fragments/spend_days.html", ctx)
    return render(request, "ledger/spends.html", ctx)


@login_required
def trends(request):
    today = _today()
    end = parse_month(request.GET.get("end"), today)
    try:
        span = max(3, min(24, int(request.GET.get("months", 12))))
    except ValueError:
        span = 12
    result = services.analysis(end, span, today=today)
    chart = {
        "labels": [m.strftime("%b %y") for m in result.months],
        "budget": [float(c.budget) for c in result.totals],
        "spent": [float(c.spent) for c in result.totals],
        "partial": [c.partial for c in result.totals],
        "funds": [
            {"name": f.category.name, "values": [float(b) for _m, b in f.balances]} for f in result.funds
        ],
    }
    return render(
        request,
        "ledger/trends.html",
        {
            "a": result,
            "chart": chart,
            "span": span,
            "end": end,
            "prev_end": add_months(end, -span),
            "next_end": add_months(end, span) if add_months(end, span) <= month_of(today) else None,
            "nav": "trends",
        },
    )


@login_required
def category_detail(request, pk):
    cat = get_object_or_404(Category, pk=pk)
    today = _today()
    month = month_of(today)
    history = services.category_history(cat, month, 12, today=today)
    if cat.is_fund:
        chart = {
            "labels": [m.strftime("%b %y") for m in history["months"]],
            "balance": [float(v) for _m, v in history["balances"]],
            "spent": [float(v) for _m, v in history["spent"]],
        }
    else:
        chart = {
            "labels": [c.month.strftime("%b %y") for c in history.cells],
            "budget": [float(c.budget) for c in history.cells],
            "spent": [float(c.spent) for c in history.cells],
        }
    recent = cat.transactions.select_related("recurring")[:30]
    return render(
        request,
        "ledger/category.html",
        {
            "cat": cat,
            "history": history,
            "chart": chart,
            "recent": recent,
            "balance": services.Book().fund_balance(cat, month) if cat.is_fund else None,
            "amount_now": cat.amount_for(month),
            "amounts": cat.amounts.order_by("-start_month"),
            "form": CategoryForm(
                instance=cat, initial={"amount": cat.amount_for(month), "from_month": month.strftime("%Y-%m")}
            ),
            "this_month": month,
            "nav": "settings",
        },
    )


# --------------------------------------------------------------------------- spends (JSON, used by the entry sheet)


@login_required
@require_POST
def spend_save(request, pk=None):
    txn = get_object_or_404(Transaction, pk=pk) if pk else Transaction(created_by=request.user)
    form = SpendForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": {k: v[0] for k, v in form.errors.items()}}, status=400)
    today = _today()
    with db_transaction.atomic():
        form.apply(txn, today)
        txn.save()
        unit = form.cleaned_data.get("repeat")
        if unit and not pk:
            rule = Recurring.objects.create(
                title=txn.title,
                amount=txn.amount,
                category=txn.category,
                note=txn.note,
                unit=unit,
                start_date=txn.date,
                month_offset=-1 if txn.month < month_of(txn.date) else 0,
                last_generated=txn.date,
                created_by=request.user,
            )
            txn.recurring = rule
            txn.save(update_fields=["recurring"])
    verb = _("updated") if pk else _("added")
    return JsonResponse(
        {
            "ok": True,
            "spend": txn.as_entry(),
            "toast": f"{txn.title} {verb}: {format_money(abs(txn.amount))}",
            "undo": None if pk else reverse("ledger:spend_delete", args=[txn.id]),
        }
    )


@login_required
@require_POST
def spend_delete(request, pk):
    txn = get_object_or_404(Transaction, pk=pk)
    data = txn.as_entry()
    txn.delete()
    return JsonResponse({"ok": True, "spend": data, "toast": _("%(title)s deleted") % {"title": data["title"]}})


@login_required
def spend_json(request, pk):
    return JsonResponse(get_object_or_404(Transaction.objects.select_related("recurring"), pk=pk).as_entry())


# --------------------------------------------------------------------------- settings: categories and budgets


@login_required
def settings_index(request):
    month = month_of(_today())
    book = services.Book()
    cats = [c for c in book.categories]
    rows = [
        {
            "cat": c,
            "amount": book.amount(c.id, month),
            "balance": book.fund_balance(c, month) if c.is_fund else None,
        }
        for c in cats
    ]
    return render(
        request,
        "ledger/settings.html",
        {
            "budget_rows": [r for r in rows if not r["cat"].is_fund and not r["cat"].archived],
            "fund_rows": [r for r in rows if r["cat"].is_fund and not r["cat"].archived],
            "archived_rows": [r for r in rows if r["cat"].archived],
            "recurring_count": Recurring.objects.filter(paused=False).count(),
            "settings_form": LedgerSettingsForm(instance=LedgerSettings.load()),
            "tokens": APIToken.objects.filter(user=request.user),
            "mcp_url": request.build_absolute_uri("/mcp"),
            "new_token": request.session.pop("new_token", None),
            "nav": "settings",
        },
    )


@login_required
def budgets_edit(request):
    """All monthly amounts on one screen, applied from a chosen month on."""
    today = _today()
    this_month = month_of(today)
    cats = list(Category.objects.filter(archived=False))
    if request.method == "POST":
        from_month = parse_month(request.POST.get("from_month"), today)
        changed = 0
        errors = {}
        with db_transaction.atomic():
            for cat in cats:
                raw = request.POST.get(f"amount_{cat.id}", "").strip().replace(",", "")
                if raw == "":
                    continue
                try:
                    value = Decimal(raw).quantize(Decimal("0.01"))
                    if value < 0:
                        raise ValueError
                except Exception:
                    errors[cat.id] = _("Enter an amount like 250.")
                    continue
                if value != cat.amount_for(from_month):
                    cat.set_amount(value, from_month)
                    changed += 1
            if errors:
                db_transaction.set_rollback(True)
        if not errors:
            messages.success(
                request,
                _("%(n)s amounts updated from %(month)s") % {"n": changed, "month": from_month.strftime("%B %Y")},
            )
            return redirect("ledger:settings")
    else:
        from_month = parse_month(request.GET.get("from_month"), today)
        errors = {}
    book = services.Book()
    return render(
        request,
        "ledger/budgets_edit.html",
        {
            "rows": [{"cat": c, "amount": book.amount(c.id, from_month), "error": errors.get(c.id)} for c in cats],
            "from_month": from_month,
            "month_choices": [add_months(this_month, i) for i in range(-12, 4)],
            "nav": "settings",
        },
    )


@login_required
def category_new(request):
    form = CategoryForm(
        request.POST or None,
        initial={"kind": request.GET.get("kind", "budget"), "from_month": _today().strftime("%Y-%m")},
    )
    if request.method == "POST" and form.is_valid():
        with db_transaction.atomic():
            cat = form.save()
            cat.set_amount(form.cleaned_data.get("amount") or Decimal("0"), form.cleaned_data.get("from_month") or _today())
        messages.success(request, _("%(name)s added") % {"name": cat.name})
        return redirect("ledger:settings")
    return render(request, "ledger/category_form.html", {"form": form, "nav": "settings"})


@login_required
@require_POST
def category_update(request, pk):
    cat = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST, instance=cat)
    if form.is_valid():
        with db_transaction.atomic():
            cat = form.save()
            amount = form.cleaned_data.get("amount")
            from_month = form.cleaned_data.get("from_month") or month_of(_today())
            if amount is not None and amount != cat.amount_for(from_month):
                cat.set_amount(amount, from_month)
        messages.success(request, _("%(name)s saved") % {"name": cat.name})
        return redirect("ledger:category", pk=cat.pk)
    return render(request, "ledger/category_form.html", {"form": form, "cat": cat, "nav": "settings"})


@login_required
@require_POST
def category_delete(request, pk):
    cat = get_object_or_404(Category, pk=pk)
    if cat.transactions.exists() or cat.recurring.exists():
        messages.error(request, _("%(name)s has spends, so it was archived instead.") % {"name": cat.name})
        cat.archived = True
        cat.save(update_fields=["archived", "updated_at"])
        return redirect("ledger:category", pk=cat.pk)
    cat.delete()
    messages.success(request, _("%(name)s deleted") % {"name": cat.name})
    return redirect("ledger:settings")


@login_required
@require_POST
def amount_delete(request, pk):
    row = get_object_or_404(MonthlyAmount, pk=pk)
    cat = row.category
    if cat.amounts.count() > 1:
        row.delete()
        messages.success(request, _("Change removed"))
    return redirect("ledger:category", pk=cat.pk)


# --------------------------------------------------------------------------- recurring


@login_required
def recurring_index(request):
    services.generate_due()
    rules = list(Recurring.objects.select_related("category"))
    for r in rules:
        r.next = None if r.paused else r.next_date()
    rules.sort(key=lambda r: (r.paused, r.next is None, r.next or _today(), r.title.lower()))
    monthly = sum(
        (
            r.amount * {"week": Decimal("52") / 12, "month": Decimal("1"), "year": Decimal("1") / 12}[r.unit] / r.every
            for r in rules
            if not r.paused and r.next
        ),
        Decimal("0"),
    )
    return render(request, "ledger/recurring.html", {"rules": rules, "monthly": monthly, "nav": "settings"})


@login_required
def recurring_form(request, pk=None):
    rule = get_object_or_404(Recurring, pk=pk) if pk else None
    initial = {} if rule else {"start_date": _today(), "every": 1, "unit": "month"}
    form = RecurringForm(request.POST or None, instance=rule, initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if not rule:
            obj.created_by = request.user
        obj.save()
        created = services.generate_due()
        msg = _("%(title)s saved") % {"title": obj.title}
        if created:
            msg += " · " + _("%(n)s entries added") % {"n": created}
        messages.success(request, msg)
        return redirect("ledger:recurring")
    return render(
        request,
        "ledger/recurring_form.html",
        {"form": form, "rule": rule, "categories": Category.objects.filter(archived=False), "nav": "settings"},
    )


@login_required
@require_POST
def recurring_toggle(request, pk):
    rule = get_object_or_404(Recurring, pk=pk)
    rule.paused = not rule.paused
    if not rule.paused:
        # Resuming skips what fell due while paused; today's entry (if any) is still made.
        yesterday = _today() - timedelta(days=1)
        if not rule.last_generated or rule.last_generated < yesterday:
            rule.last_generated = yesterday
    rule.save(update_fields=["paused", "last_generated", "updated_at"])
    services.generate_due()
    messages.success(request, (_("%(t)s paused") if rule.paused else _("%(t)s resumed")) % {"t": rule.title})
    return redirect("ledger:recurring")


@login_required
@require_POST
def recurring_delete(request, pk):
    rule = get_object_or_404(Recurring, pk=pk)
    title = rule.title
    rule.delete()  # past entries stay; they just lose the link
    messages.success(request, _("%(t)s deleted. Past entries were kept.") % {"t": title})
    return redirect("ledger:recurring")


# --------------------------------------------------------------------------- household settings, tokens, auth


@login_required
@require_POST
def settings_save(request):
    form = LedgerSettingsForm(request.POST, instance=LedgerSettings.load())
    if form.is_valid():
        form.save()
        messages.success(request, _("Settings saved"))
    return redirect("ledger:settings")


@login_required
@require_POST
def token_create(request):
    name = request.POST.get("name", "").strip() or _("Agent")
    scope = request.POST.get("scope")
    if scope not in APIToken.Scope.values:
        scope = APIToken.Scope.READ_ONLY
    token = APIToken.objects.create(user=request.user, name=name, scope=scope)
    request.session["new_token"] = {"name": token.name, "key": token.key}
    return redirect(reverse("ledger:settings") + "#agents")


@login_required
@require_POST
def token_delete(request, pk):
    get_object_or_404(APIToken, pk=pk, user=request.user).delete()
    messages.success(request, _("Token revoked"))
    return redirect(reverse("ledger:settings") + "#agents")


def logout_view(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    logout(request)
    return redirect(settings.LOGIN_URL)
