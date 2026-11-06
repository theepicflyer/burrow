"""Budget and fund maths, analysis, and recurring generation.

``Book`` loads every monthly amount and every (category, month) total once, so
pages that look across many months and categories cost two queries.
"""

from __future__ import annotations

import bisect
import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Case, Count, DecimalField, F, Max, Sum, When
from django.utils import timezone

from apps.ledger.models import Category, MonthlyAmount, Recurring, Transaction, Type
from apps.ledger.months import add_months, month_of, month_range

ZERO = Decimal("0")


def net_amount():
    """Net spend of a transaction row: the amount for an expense, minus it for income."""
    return Case(
        When(type=Type.INCOME, then=-F("amount")),
        default=F("amount"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


class Book:
    def __init__(self):
        self.categories = list(Category.objects.all())
        self.by_id = {c.id: c for c in self.categories}
        self._starts: dict[int, list[date]] = defaultdict(list)
        self._amounts: dict[int, list[Decimal]] = defaultdict(list)
        for cat_id, start, amount in MonthlyAmount.objects.order_by("category_id", "start_month").values_list(
            "category_id", "start_month", "amount"
        ):
            self._starts[cat_id].append(start)
            self._amounts[cat_id].append(amount)
        self._spent: dict[tuple[int, date], Decimal] = {}
        self._spent_by_cat: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)
        # Net spend per (category, month). For an income category it is negative:
        # ``received`` flips the sign.
        rows = Transaction.objects.values("category_id", "month").annotate(total=Sum(net_amount())).order_by("month")
        for row in rows:
            self._spent[(row["category_id"], row["month"])] = row["total"]
            self._spent_by_cat[row["category_id"]].append((row["month"], row["total"]))

    def amount(self, cat_id: int, month: date) -> Decimal:
        starts = self._starts.get(cat_id)
        if not starts:
            return ZERO
        i = bisect.bisect_right(starts, month) - 1
        return self._amounts[cat_id][i] if i >= 0 else ZERO

    def spent(self, cat_id: int, month: date) -> Decimal:
        return self._spent.get((cat_id, month), ZERO)

    def received(self, cat_id: int, month: date) -> Decimal:
        return -self.spent(cat_id, month)

    def first_month(self, cat_id: int) -> date | None:
        starts = self._starts.get(cat_id)
        return starts[0] if starts else None

    def topups_through(self, cat_id: int, month: date) -> Decimal:
        first = self.first_month(cat_id)
        if first is None or first > month:
            return ZERO
        return sum((self.amount(cat_id, m) for m in month_range(first, month)), ZERO)

    def spent_through(self, cat_id: int, month: date) -> Decimal:
        return sum((t for m, t in self._spent_by_cat.get(cat_id, []) if m <= month), ZERO)

    def fund_balance(self, cat: Category, month: date) -> Decimal:
        """Balance at the end of ``month`` (top-ups land on the 1st)."""
        return cat.opening_balance + self.topups_through(cat.id, month) - self.spent_through(cat.id, month)

    def has_activity(self, cat_id: int, months: list[date]) -> bool:
        return any((cat_id, m) in self._spent for m in months)


# --------------------------------------------------------------------------- month


@dataclass
class BudgetLine:
    category: Category
    budget: Decimal
    spent: Decimal

    @property
    def left(self) -> Decimal:
        return self.budget - self.spent

    @property
    def over(self) -> bool:
        return self.spent > self.budget

    @property
    def percent(self) -> int:
        if self.budget <= 0:
            return 100 if self.spent > 0 else 0
        return int(round(self.spent / self.budget * 100))


@dataclass
class FundLine:
    category: Category
    topup: Decimal
    spent: Decimal
    balance: Decimal

    @property
    def acorns(self) -> int:
        """0-15 acorns for the Stash art: share of the target, or of a year of top-ups."""
        cap = self.category.target or (self.topup * 12)
        if cap <= 0 or self.balance <= 0:
            return 0
        return max(1, min(15, int(round(self.balance / cap * 15))))


@dataclass
class IncomeLine:
    category: Category
    received: Decimal


@dataclass
class MonthStatus:
    month: date
    budgets: list[BudgetLine]
    funds: list[FundLine]
    incomes: list[IncomeLine] = field(default_factory=list)
    days_left: int | None = None  # set for the current month only
    elapsed: float | None = None  # share of the month gone, current month only

    @property
    def total_budget(self) -> Decimal:
        return sum((b.budget for b in self.budgets), ZERO)

    @property
    def total_spent(self) -> Decimal:
        return sum((b.spent for b in self.budgets), ZERO)

    @property
    def left(self) -> Decimal:
        return self.total_budget - self.total_spent

    @property
    def over(self) -> bool:
        return self.total_spent > self.total_budget

    @property
    def percent(self) -> int:
        return BudgetLine(None, self.total_budget, self.total_spent).percent

    @property
    def fund_spent(self) -> Decimal:
        return sum((f.spent for f in self.funds), ZERO)

    @property
    def income(self) -> Decimal:
        return sum((i.received for i in self.incomes), ZERO)

    @property
    def out(self) -> Decimal:
        """Everything spent: budgets and funds, net of money back."""
        return self.total_spent + self.fund_spent

    @property
    def net(self) -> Decimal:
        return self.income - self.out

    @property
    def leaves(self) -> int:
        """0-26 leaves for the wreath."""
        if self.total_budget <= 0:
            return 0
        return min(26, int(round(self.total_spent / self.total_budget * 26)))

    @property
    def ahead_of_pace(self) -> bool:
        """Spent more than the share of the month gone by (current month only)."""
        if self.elapsed is None or self.total_budget <= 0:
            return False
        return self.total_spent > self.total_budget * Decimal(str(self.elapsed))


def month_status(month: date, book: Book | None = None, today: date | None = None) -> MonthStatus:
    book = book or Book()
    month = month_of(month)
    today = today or timezone.localdate()
    budgets, funds, incomes = [], [], []
    for cat in book.categories:
        spent = book.spent(cat.id, month)
        if cat.archived and not spent:
            continue
        if cat.is_income:
            if spent or not cat.archived:
                incomes.append(IncomeLine(cat, -spent))
        elif cat.is_fund:
            funds.append(FundLine(cat, book.amount(cat.id, month), spent, book.fund_balance(cat, month)))
        else:
            budget = book.amount(cat.id, month)
            if budget or spent or not cat.archived:
                budgets.append(BudgetLine(cat, budget, spent))
    status = MonthStatus(month, budgets, funds, incomes)
    if month == month_of(today):
        days = calendar.monthrange(month.year, month.month)[1]
        status.days_left = days - today.day
        status.elapsed = today.day / days
    return status


# --------------------------------------------------------------------------- analysis


@dataclass
class Cell:
    month: date
    budget: Decimal
    spent: Decimal
    partial: bool = False  # the month is still running

    @property
    def over(self) -> bool:
        return self.spent > self.budget

    @property
    def percent(self) -> int | None:
        if self.budget <= 0:
            return None
        return int(round(self.spent / self.budget * 100))

    @property
    def tone(self) -> str:
        if self.spent <= 0 and self.budget <= 0:
            return "none"
        if self.over:
            return "over"
        if self.budget > 0 and self.spent >= self.budget * Decimal("0.9"):
            return "near"
        return "under"


@dataclass
class CategoryTrend:
    category: Category
    cells: list[Cell]
    budget_now: Decimal

    @property
    def complete(self) -> list[Cell]:
        """Finished months in which the category had a budget or spending."""
        return [c for c in self.cells if not c.partial and (c.budget > 0 or c.spent != 0)]

    @property
    def months_over(self) -> int:
        return sum(1 for c in self.complete if c.over)

    @property
    def months_counted(self) -> int:
        return len(self.complete)

    @property
    def avg_spent(self) -> Decimal:
        cells = self.complete
        return (sum((c.spent for c in cells), ZERO) / len(cells)).quantize(Decimal("0.01")) if cells else ZERO

    @property
    def avg_budget(self) -> Decimal:
        cells = self.complete
        return (sum((c.budget for c in cells), ZERO) / len(cells)).quantize(Decimal("0.01")) if cells else ZERO

    @property
    def total_over(self) -> Decimal:
        return sum((c.spent - c.budget for c in self.complete if c.over), ZERO)

    @property
    def avg_percent(self) -> int | None:
        if self.avg_budget <= 0:
            return None
        return int(round(self.avg_spent / self.avg_budget * 100))

    @property
    def avg_pct(self) -> int:
        return self.avg_percent or 0

    @property
    def avg_over(self) -> bool:
        return self.avg_spent > self.avg_budget

    @property
    def consistently_over(self) -> bool:
        """Over in at least half of the complete months (and at least twice)."""
        n = self.months_counted
        return n > 0 and self.months_over >= max(2, (n + 1) // 2)


@dataclass
class FundTrend:
    category: Category
    balances: list[tuple[date, Decimal]]
    topup_now: Decimal
    avg_spent: Decimal

    @property
    def balance_now(self) -> Decimal:
        return self.balances[-1][1] if self.balances else self.category.opening_balance

    @property
    def draining(self) -> bool:
        """Spending more on average than the top-up puts in."""
        return self.avg_spent > self.topup_now


@dataclass
class Flow:
    """Money in and out in one month. ``out`` is budgets and funds, net of money back."""

    month: date
    income: Decimal
    out: Decimal
    partial: bool = False

    @property
    def net(self) -> Decimal:
        return self.income - self.out


@dataclass
class Analysis:
    months: list[date]
    categories: list[CategoryTrend]
    totals: list[Cell]
    funds: list[FundTrend]
    current: date | None = None
    flagged: list[CategoryTrend] = field(default_factory=list)
    flows: list[Flow] = field(default_factory=list)

    def _avg(self, values: list[Decimal]) -> Decimal:
        return (sum(values, ZERO) / len(values)).quantize(Decimal("0.01")) if values else ZERO

    @property
    def complete_flows(self) -> list[Flow]:
        return [f for f in self.flows if not f.partial and (f.income or f.out)]

    @property
    def avg_income(self) -> Decimal:
        return self._avg([f.income for f in self.complete_flows])

    @property
    def avg_out(self) -> Decimal:
        return self._avg([f.out for f in self.complete_flows])

    @property
    def avg_net(self) -> Decimal:
        return self._avg([f.net for f in self.complete_flows])

    @property
    def complete_totals(self) -> list[Cell]:
        return [c for c in self.totals if not c.partial and (c.budget > 0 or c.spent != 0)]

    @property
    def months_over(self) -> int:
        return sum(1 for c in self.complete_totals if c.over)

    @property
    def avg_spent(self) -> Decimal:
        cells = self.complete_totals
        return (sum((c.spent for c in cells), ZERO) / len(cells)).quantize(Decimal("0.01")) if cells else ZERO

    @property
    def avg_budget(self) -> Decimal:
        cells = self.complete_totals
        return (sum((c.budget for c in cells), ZERO) / len(cells)).quantize(Decimal("0.01")) if cells else ZERO


def analysis(end_month: date, months: int = 12, today: date | None = None) -> Analysis:
    today = today or timezone.localdate()
    end_month = month_of(end_month)
    span = month_range(add_months(end_month, -(months - 1)), end_month)
    current = month_of(today)
    book = Book()

    # Don't open the range on months from before the ledger has anything in them.
    first_data = min(
        [m for cat_id, m in book._spent] + [starts[0] for starts in book._starts.values() if starts],
        default=None,
    )
    if first_data and first_data > span[0]:
        span = [m for m in span if m >= first_data] or span[-1:]

    trends = []
    for cat in book.categories:
        if cat.is_fund or cat.is_income:
            continue
        if cat.archived and not book.has_activity(cat.id, span):
            continue
        cells = [Cell(m, book.amount(cat.id, m), book.spent(cat.id, m), partial=m >= current) for m in span]
        if not any(c.budget or c.spent for c in cells):
            continue
        trends.append(CategoryTrend(cat, cells, book.amount(cat.id, current)))

    totals = []
    for i, m in enumerate(span):
        totals.append(
            Cell(
                m,
                sum((t.cells[i].budget for t in trends), ZERO),
                sum((t.cells[i].spent for t in trends), ZERO),
                partial=m >= current,
            )
        )

    funds = []
    complete = [m for m in span if m < current]
    for cat in book.categories:
        if not cat.is_fund or (cat.archived and not book.has_activity(cat.id, span)):
            continue
        balances = [(m, book.fund_balance(cat, m)) for m in span]
        spent = [book.spent(cat.id, m) for m in complete]
        avg = (sum(spent, ZERO) / len(spent)).quantize(Decimal("0.01")) if spent else ZERO
        funds.append(FundTrend(cat, balances, book.amount(cat.id, current), avg))

    trends.sort(key=lambda t: (-t.months_over, -(t.avg_percent or 0), t.category.name))
    result = Analysis(span, trends, totals, funds, current if current in span else None)
    result.flagged = [t for t in trends if t.consistently_over]
    for m in span:
        income = sum((book.received(c.id, m) for c in book.categories if c.is_income), ZERO)
        out = sum((book.spent(c.id, m) for c in book.categories if not c.is_income), ZERO)
        result.flows.append(Flow(m, income, out, partial=m >= current))
    return result


def category_history(cat: Category, end_month: date, months: int = 12, today: date | None = None):
    """Per-month budget/spent (budgets) or balance (funds) for one category."""
    today = today or timezone.localdate()
    current = month_of(today)
    span = month_range(add_months(end_month, -(months - 1)), end_month)
    book = Book()
    if cat.is_income:
        return {"months": span, "received": [(m, book.received(cat.id, m)) for m in span]}
    if cat.is_fund:
        return {
            "months": span,
            "balances": [(m, book.fund_balance(cat, m)) for m in span],
            "topups": [(m, book.amount(cat.id, m)) for m in span],
            "spent": [(m, book.spent(cat.id, m)) for m in span],
        }
    return CategoryTrend(
        cat, [Cell(m, book.amount(cat.id, m), book.spent(cat.id, m), partial=m >= current) for m in span],
        book.amount(cat.id, current),
    )


# --------------------------------------------------------------------------- entry helpers


def categories_for_entry(days: int = 90) -> list[Category]:
    """Active categories, most used in the last ``days`` first, then by name. The entry
    flow shows income categories first when entering income."""
    since = timezone.localdate() - timedelta(days=days)
    counts = dict(
        Transaction.objects.filter(date__gte=since)
        .values("category_id")
        .annotate(n=Count("id"))
        .values_list("category_id", "n")
    )
    cats = list(Category.objects.filter(archived=False))
    cats.sort(key=lambda c: (-counts.get(c.id, 0), c.kind != Category.Kind.BUDGET, c.name.lower()))
    return cats


def title_suggestions(limit: int = 300) -> list[dict]:
    """Recent distinct titles with the category and type last used for each, newest first."""
    rows = (
        Transaction.objects.values("title")
        .annotate(last=Max("id"))
        .order_by("-last")[:limit]
    )
    last_ids = [r["last"] for r in rows]
    by_id = {i: (c, y) for i, c, y in Transaction.objects.filter(id__in=last_ids).values_list("id", "category_id", "type")}
    out = []
    for r in rows:
        cat, kind = by_id.get(r["last"], (None, Type.EXPENSE))
        out.append({"t": r["title"], "c": cat, "y": kind})
    return out


# --------------------------------------------------------------------------- recurring


def generate_due(today: date | None = None) -> int:
    """Create every recurring entry that has fallen due. Safe to call often."""
    today = today or timezone.localdate()
    created = 0
    with db_transaction.atomic():
        rules = Recurring.objects.select_for_update().filter(paused=False, start_date__lte=today)
        for rule in rules:
            after = rule.last_generated or (rule.start_date - timedelta(days=1))
            dates = rule.dates_between(after, today)
            for d in dates:
                Transaction.objects.create(
                    type=rule.type,
                    amount=rule.amount,
                    title=rule.title,
                    category=rule.category,
                    date=d,
                    month=rule.month_for(d),
                    note=rule.note,
                    recurring=rule,
                    created_by=rule.created_by,
                )
            if dates:
                rule.last_generated = dates[-1]
                rule.save(update_fields=["last_generated", "updated_at"])
                created += len(dates)
    return created


def upcoming(until: date, today: date | None = None) -> list[tuple[date, Recurring]]:
    """Recurring entries due after today up to ``until``, soonest first."""
    today = today or timezone.localdate()
    out = []
    for rule in Recurring.objects.filter(paused=False).select_related("category"):
        after = max(today, rule.last_generated) if rule.last_generated else max(today, rule.start_date - timedelta(days=1))
        for d in rule.dates_between(after, until):
            out.append((d, rule))
    out.sort(key=lambda x: (x[0], x[1].title))
    return out
