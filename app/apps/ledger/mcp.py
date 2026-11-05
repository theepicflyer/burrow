"""MCP tools over the household ledger, published at ``/mcp``.

django-mcp-server autodiscovers this module and registers every public method
of ``LedgerTools`` as a tool: the method name is the tool name, its docstring
the description the client's model reads, and its signature the input schema.

Access. ``/mcp`` itself only lets in an authenticated, non-demo user (see
``apps.mcp.urls``). A hand-written toolset has no DRF permission layer, so each
tool is wrapped by ``_tool``, which checks the caller before the tool runs:

* an ``APIToken`` (``request.auth``) with scope ``read_only`` may not use a
  write tool;
* an OAuth ``AccessToken`` needs ``mcp:read`` for read tools and ``mcp:write``
  for write tools;
* a session or DRF authtoken user may use every tool (as on ``/api/``).

``LedgerTools._add_tools_to`` refuses to register a public method that is not
wrapped by ``_tool``, so a new tool cannot skip the check.

The ledger is shared: every signed-in user sees and edits all of it, so there is
no owner filtering. Mistakes in the input come back as an MCP error result
(``isError``) with a message the model can act on, not as a raw exception.
"""

import functools
import re
import zoneinfo
from datetime import date as Date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q, Sum
from django.utils import timezone
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from mcp_server import MCPToolset
from mcp_server import mcp_server as global_mcp_server
from oauth2_provider.models import get_access_token_model

from apps.api.models import APIToken
from apps.ledger import services
from apps.ledger.models import Category, LedgerSettings, Recurring, Transaction
from apps.ledger.months import month_of

READ_SCOPE = "mcp:read"
WRITE_SCOPE = "mcp:write"
MAX_LIMIT = 500
MAX_ANALYSIS_MONTHS = 36
ZERO = Decimal("0")
CENT = Decimal("0.01")

INSTRUCTIONS = """\
Burrow is a household spending ledger, shared by everyone in the household. \
It is a list of spends; each transaction sits in one category. Budget \
categories have a monthly budget; fund categories are sinking funds topped up \
on the 1st of each month and drawn down by what is spent from them. A \
transaction has a date (when it happened) and a month it counts toward \
(normally the date's month). Positive amounts are money spent, negative \
amounts are refunds or money paid into a fund. Call get_ledger_info first for \
today's date, the currency and these conventions; look up category ids with \
list_categories before add_transaction."""

global_mcp_server.append_instructions(INSTRUCTIONS)


# --------------------------------------------------------------------------- access


class ToolInputError(Exception):
    """A caller mistake, reported back to the client as an error result."""


def access_error(request, write: bool) -> str | None:
    """Why ``request`` may not use a read (or write) tool, or ``None`` if it may."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return "Not signed in. Connect to Burrow with an API token or OAuth."
    token = getattr(request, "auth", None)
    if isinstance(token, APIToken):
        if write and token.is_read_only:
            return (
                "This API token is read-only, so it cannot change the ledger. "
                "Use a read-and-write token to add, edit or delete transactions."
            )
    elif isinstance(token, get_access_token_model()):
        scope = WRITE_SCOPE if write else READ_SCOPE
        if not token.allow_scopes([scope]):
            action = "change" if write else "read"
            return (
                f"This connection was not granted the {scope} scope, so it cannot "
                f"{action} the ledger. Reconnect and allow {scope}."
            )
    return None


def _error(message: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=message)], isError=True)


def _tool(*, write: bool = False, destructive: bool = False, idempotent: bool = True):
    """Mark a ``LedgerTools`` method as a tool: check access first, and turn a
    ``ToolInputError`` into an error result."""
    annotations = ToolAnnotations(
        readOnlyHint=not write,
        destructiveHint=destructive,
        idempotentHint=idempotent,
        openWorldHint=False,
    )

    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            denied = access_error(self.request, write)
            if denied:
                return _error(denied)
            try:
                return fn(self, *args, **kwargs)
            except ToolInputError as exc:
                return _error(str(exc))

        wrapper.ledger_tool_annotations = annotations
        return wrapper

    return decorate


# --------------------------------------------------------------------------- parsing

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_MONTH_RE = re.compile(r"(\d{4})-(\d{2})(?:-\d{2})?")


def _parse_date(value: str, field: str = "date") -> Date:
    text = value.strip() if isinstance(value, str) else ""
    if _DATE_RE.fullmatch(text):
        try:
            return Date.fromisoformat(text)
        except ValueError:
            pass
    raise ToolInputError(f"{field} must be a date like 2026-05-20 (YYYY-MM-DD); got {value!r}.")


def _parse_month(value: str, field: str = "month") -> Date:
    match = _MONTH_RE.fullmatch(value.strip()) if isinstance(value, str) else None
    if match:
        try:
            return Date(int(match[1]), int(match[2]), 1)
        except ValueError:
            pass
    raise ToolInputError(f"{field} must be a month like 2026-05 (YYYY-MM); got {value!r}.")


def _parse_amount(value) -> Decimal:
    bad = ToolInputError(
        f"amount must be a plain number with at most 2 decimal places, like 12.50 or -3; got {value!r}."
    )
    if isinstance(value, bool):
        raise bad
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation:
        raise bad from None
    if not amount.is_finite() or abs(amount) >= Decimal("1e12"):
        raise bad
    if amount != amount.quantize(CENT):
        raise bad
    if not amount:
        raise ToolInputError("amount must not be zero.")
    return amount.quantize(CENT)


def _clean_title(value: str) -> str:
    title = (value or "").strip()
    if not title:
        raise ToolInputError("title must not be empty.")
    if len(title) > 200:
        raise ToolInputError("title must be at most 200 characters; put the rest in note.")
    return title


def _get_category(category_id: int, *, for_entry: bool = False) -> Category:
    category = Category.objects.filter(pk=category_id).first()
    if category is None:
        raise ToolInputError(f"There is no category with id {category_id}. Call list_categories for the ids.")
    if for_entry and category.archived:
        raise ToolInputError(
            f"Category {category.name!r} (id {category.id}) is archived and takes no new "
            f"transactions. Pick an active category from list_categories."
        )
    return category


def _get_transaction(transaction_id: int) -> Transaction:
    tx = Transaction.objects.select_related("category", "created_by").filter(pk=transaction_id).first()
    if tx is None:
        raise ToolInputError(f"There is no transaction with id {transaction_id}. Use list_transactions to find it.")
    return tx


# --------------------------------------------------------------------------- output


def _money(value: Decimal) -> str:
    return f"{(value or ZERO) + ZERO:.2f}"


def _month(value: Date) -> str:
    return value.strftime("%Y-%m")


def _user(user) -> dict | None:
    if user is None:
        return None
    return {"email": user.email, "name": user.get_full_name()}


def _transaction(tx: Transaction) -> dict:
    return {
        "id": tx.id,
        "date": tx.date.isoformat(),
        "month": _month(tx.month),
        "title": tx.title,
        "amount": _money(tx.amount),
        "category": {"id": tx.category_id, "name": tx.category.name, "kind": tx.category.kind},
        "note": tx.note,
        "recurring_id": tx.recurring_id,
        "created_by": _user(tx.created_by),
    }


def _category_month(category: Category, month: Date) -> dict:
    """Where ``category`` stands for ``month``: a budget's budget/spent/left, or a
    fund's top-up/spent/month-end balance."""
    book = services.Book()
    spent = book.spent(category.id, month)
    out = {"category_id": category.id, "name": category.name, "kind": category.kind, "month": _month(month)}
    if category.is_fund:
        out |= {
            "topup": _money(book.amount(category.id, month)),
            "spent": _money(spent),
            "balance": _money(book.fund_balance(category, month)),
        }
    else:
        budget = book.amount(category.id, month)
        out |= {
            "budget": _money(budget),
            "spent": _money(spent),
            "left": _money(budget - spent),
            "over": spent > budget,
        }
    return out


def _cell(cell: services.Cell) -> dict:
    return {
        "month": _month(cell.month),
        "budget": _money(cell.budget),
        "spent": _money(cell.spent),
        "over": cell.over,
        "partial": cell.partial,
    }


# --------------------------------------------------------------------------- tools


class LedgerTools(MCPToolset):
    """Read the household ledger and, with write access, log spends."""

    def _add_tools_to(self, tool_manager):
        tools = super()._add_tools_to(tool_manager)
        for tool in tools:
            annotations = getattr(getattr(type(self), tool.name, None), "ledger_tool_annotations", None)
            if annotations is None:
                raise ImproperlyConfigured(f"Ledger MCP tool {tool.name!r} must be decorated with @_tool.")
            tool.annotations = annotations
        return tools

    def _today(self) -> Date:
        """Today in the caller's timezone setting, else the server's TIME_ZONE.
        (Token-authenticated requests reach the view as anonymous, so the
        localization middleware never activated the user's timezone.)"""
        tz = timezone.get_default_timezone()
        name = getattr(getattr(self.request.user, "settings", None), "timezone", "auto")
        if name and name != "auto":
            try:
                tz = zoneinfo.ZoneInfo(name)
            except (zoneinfo.ZoneInfoNotFoundError, ValueError):
                pass
        return timezone.localdate(timezone=tz)

    def _start(self) -> Date:
        """Create any recurring entries that have fallen due; return today."""
        today = self._today()
        services.generate_due(today=today)
        return today

    # ----------------------------------------------------------------- read

    @_tool()
    def get_ledger_info(self) -> dict:
        """Start here. Returns the ledger's currency symbol, today's date and the
        current month (in the household's timezone), who you are signed in as,
        whether this connection may change the ledger (can_write), and how the
        ledger's fields work. Call it before the other tools."""
        today = self._today()
        return {
            "currency": LedgerSettings.load().currency,
            "today": today.isoformat(),
            "current_month": _month(today),
            "signed_in_as": _user(self.request.user),
            "can_write": access_error(self.request, write=True) is None,
            "conventions": {
                "shared": "One ledger shared by the whole household; everyone sees and edits everything.",
                "amount": (
                    "Strings with 2 decimal places in the ledger's currency. Positive = money spent; "
                    "negative = money back (a refund, or money paid into a fund)."
                ),
                "date": "YYYY-MM-DD: the day the spend happened or was billed.",
                "month": (
                    "YYYY-MM: the month a transaction counts toward. It is the date's month unless "
                    "set otherwise (May's bill paid on 10 June can count toward May). Budgets and "
                    "summaries use this month, not the date."
                ),
                "category_kinds": {
                    "budget": "Everyday spending with a monthly budget; spending is compared to it.",
                    "fund": (
                        "A sinking fund: topped up by a monthly amount on the 1st, lowered by what "
                        "is spent from it. Its balance carries over from month to month."
                    ),
                },
                "monthly_amount": (
                    "A category's budget (or a fund's top-up) for a month. Changes apply from a "
                    "given month on; earlier months keep the amount they had."
                ),
                "recurring": (
                    "Recurring rules create their transaction on each scheduled date once it arrives; "
                    "nothing is created ahead of time."
                ),
            },
        }

    @_tool()
    def list_categories(self, include_archived: bool = False) -> dict:
        """List the spending categories. Every transaction belongs to exactly one
        category, so use this to find the category_id for add_transaction.

        Each category has kind "budget" (everyday spending with a monthly budget)
        or "fund" (a sinking fund, topped up by a fixed amount on the 1st of each
        month; spending from it lowers its balance). monthly_amount is this
        month's budget, or this month's top-up for a fund. Funds also return
        balance (the balance at the end of the current month: this month's
        top-up is in, and everything spent from it so far is out) and target
        (what it is saving up to, or null).

        Args:
            include_archived: also return archived categories, which no longer
                take new transactions. Default false.
        """
        today = self._start()
        current = month_of(today)
        book = services.Book()
        out = []
        for cat in book.categories:
            if cat.archived and not include_archived:
                continue
            row = {
                "id": cat.id,
                "name": cat.name,
                "kind": cat.kind,
                "archived": cat.archived,
                "monthly_amount": _money(book.amount(cat.id, current)),
            }
            if cat.is_fund:
                row["balance"] = _money(book.fund_balance(cat, current))
                row["target"] = _money(cat.target) if cat.target is not None else None
            out.append(row)
        return {"month": _month(current), "categories": out}

    @_tool()
    def list_transactions(
        self,
        month: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        category_id: int | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """Search and list transactions, newest date first. Filters combine; leave
        them all out to list everything.

        Args:
            month: "YYYY-MM"; only transactions that count toward this month. Use
                this (not dates) to see what a month's budgets were spent on.
            date_from: "YYYY-MM-DD"; only transactions dated on or after this day.
            date_to: "YYYY-MM-DD"; only transactions dated on or before this day.
            category_id: only this category (ids from list_categories).
            search: case-insensitive text to find in the title or note.
            limit: page size, default 100, at most 500.
            offset: how many matching transactions to skip, for paging.

        Returns total (how many transactions match), total_amount (the sum of
        every matching amount, not just this page), has_more, and the page of
        transactions. Each has id, date (when it happened), month (the month it
        counts toward), title, amount (positive = spent, negative = refund or
        money paid into a fund), category, note, recurring_id (the recurring
        rule that created it, or null) and created_by.
        """
        self._start()
        qs = Transaction.objects.select_related("category", "created_by")
        if month:
            qs = qs.filter(month=_parse_month(month))
        start = _parse_date(date_from, "date_from") if date_from else None
        end = _parse_date(date_to, "date_to") if date_to else None
        if start and end and start > end:
            raise ToolInputError("date_from is after date_to.")
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        if category_id is not None:
            qs = qs.filter(category=_get_category(category_id))
        if search and search.strip():
            text = search.strip()
            qs = qs.filter(Q(title__icontains=text) | Q(note__icontains=text))
        if offset < 0:
            raise ToolInputError("offset must be 0 or more.")
        limit = max(1, min(limit, MAX_LIMIT))

        total = qs.count()
        page = [_transaction(tx) for tx in qs[offset : offset + limit]]
        return {
            "total": total,
            "total_amount": _money(qs.aggregate(total=Sum("amount"))["total"]),
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(page) < total,
            "transactions": page,
        }

    @_tool()
    def get_month_summary(self, month: str | None = None) -> dict:
        """How the household is doing against its budgets in one month.

        Args:
            month: "YYYY-MM"; defaults to the current month.

        Returns budgets: for each budget category, budget, spent (net of
        refunds), left (budget minus spent; negative when over), over and
        percent_used; budget_totals across all budget categories; and funds: for
        each fund, topup (this month's top-up), spent (spent from it this month)
        and balance (its balance at the end of the month). Spending counts by
        the month a transaction counts toward, not its date. Fund spending is
        not part of budget_totals. Archived categories only appear when they
        have spending that month. For the current month it also returns
        days_left, elapsed (share of the month gone, 0-1) and, in
        budget_totals, ahead_of_pace (a larger share of the total budget is
        spent than the share of the month that has passed).
        """
        today = self._start()
        target = _parse_month(month) if month else month_of(today)
        status = services.month_status(target, today=today)
        totals = {
            "budget": _money(status.total_budget),
            "spent": _money(status.total_spent),
            "left": _money(status.left),
            "over": status.over,
            "percent_used": status.percent,
        }
        out = {
            "month": _month(target),
            "is_current_month": target == month_of(today),
            "currency": LedgerSettings.load().currency,
            "budgets": [
                {
                    "category_id": line.category.id,
                    "name": line.category.name,
                    "budget": _money(line.budget),
                    "spent": _money(line.spent),
                    "left": _money(line.left),
                    "over": line.over,
                    "percent_used": line.percent,
                }
                for line in status.budgets
            ],
            "budget_totals": totals,
            "funds": [
                {
                    "category_id": line.category.id,
                    "name": line.category.name,
                    "topup": _money(line.topup),
                    "spent": _money(line.spent),
                    "balance": _money(line.balance),
                    "target": _money(line.category.target) if line.category.target is not None else None,
                }
                for line in status.funds
            ],
            "fund_spent_total": _money(status.fund_spent),
        }
        if status.days_left is not None:
            out["days_left"] = status.days_left
            out["elapsed"] = round(status.elapsed, 2)
            totals["ahead_of_pace"] = status.ahead_of_pace
        return out

    @_tool()
    def get_budget_analysis(self, end_month: str | None = None, months: int = 12) -> dict:
        """Spending against budget over several months, to spot budget categories
        that keep running over and funds that are draining.

        Args:
            end_month: "YYYY-MM", the last month of the window; defaults to the
                current month.
            months: how many months the window covers, ending at end_month
                (1-36, default 12).

        Months that are still running (the current month, and any later one)
        are marked partial: true and left out of every count and average below.

        Returns months (the window); categories: for each budget category its
        per-month budget/spent/over, then over the complete months
        months_over, months_counted, avg_spent, avg_budget, avg_percent,
        total_over and consistently_over (over budget in at least half of the
        complete months, and at least twice), sorted most-over first; totals:
        the same per month summed over all budget categories, with
        months_over, avg_spent and avg_budget; funds: each fund's month-end
        balance per month, topup_now, avg_spent (average monthly spending over
        the complete months) and draining (spending more on average than the
        top-up puts in); and flagged: the consistently-over categories.
        """
        today = self._start()
        end = _parse_month(end_month, "end_month") if end_month else month_of(today)
        if not 1 <= months <= MAX_ANALYSIS_MONTHS:
            raise ToolInputError(f"months must be between 1 and {MAX_ANALYSIS_MONTHS}.")
        result = services.analysis(end, months=months, today=today)
        return {
            "months": [_month(m) for m in result.months],
            "current_month": _month(result.current) if result.current else None,
            "currency": LedgerSettings.load().currency,
            "categories": [
                {
                    "category_id": t.category.id,
                    "name": t.category.name,
                    "budget_now": _money(t.budget_now),
                    "months_over": t.months_over,
                    "months_counted": t.months_counted,
                    "avg_spent": _money(t.avg_spent),
                    "avg_budget": _money(t.avg_budget),
                    "avg_percent": t.avg_percent,
                    "total_over": _money(t.total_over),
                    "consistently_over": t.consistently_over,
                    "by_month": [_cell(c) for c in t.cells],
                }
                for t in result.categories
            ],
            "totals": {
                "months_over": result.months_over,
                "avg_spent": _money(result.avg_spent),
                "avg_budget": _money(result.avg_budget),
                "by_month": [_cell(c) for c in result.totals],
            },
            "funds": [
                {
                    "category_id": f.category.id,
                    "name": f.category.name,
                    "topup_now": _money(f.topup_now),
                    "avg_spent": _money(f.avg_spent),
                    "draining": f.draining,
                    "balance_at_end": _money(f.balance_now),
                    "target": _money(f.category.target) if f.category.target is not None else None,
                    "balances": [{"month": _month(m), "balance": _money(b)} for m, b in f.balances],
                }
                for f in result.funds
            ],
            "flagged": [{"category_id": t.category.id, "name": t.category.name} for t in result.flagged],
        }

    @_tool()
    def list_recurring(self) -> dict:
        """List the recurring spend rules (subscriptions, bills, allowances). A
        rule creates its transaction on each date of its schedule once that date
        arrives; nothing is created ahead of time.

        Each rule has its title, amount, category and note; its schedule (every
        N week/month/year from start_date, until end_date if set); next_date
        (when it will create its next transaction; null once the schedule has
        ended); counts_toward ("same month", or "previous month" for a bill that
        arrives after the month it belongs to) with next_counts_toward (the
        month next_date's entry will count toward); and paused (a paused rule
        creates nothing until it is resumed in the app). Rules cannot be edited
        through these tools.
        """
        self._start()
        out = []
        for rule in Recurring.objects.select_related("category"):
            next_date = rule.next_date()
            out.append(
                {
                    "id": rule.id,
                    "title": rule.title,
                    "amount": _money(rule.amount),
                    "category": {"id": rule.category_id, "name": rule.category.name, "kind": rule.category.kind},
                    "note": rule.note,
                    "every": rule.every,
                    "unit": rule.unit,
                    "frequency": str(rule.frequency_label),
                    "start_date": rule.start_date.isoformat(),
                    "end_date": rule.end_date.isoformat() if rule.end_date else None,
                    "next_date": next_date.isoformat() if next_date else None,
                    "next_counts_toward": _month(rule.month_for(next_date)) if next_date else None,
                    "counts_toward": "previous month" if rule.month_offset == -1 else "same month",
                    "month_offset": rule.month_offset,
                    "paused": rule.paused,
                    "last_created": rule.last_generated.isoformat() if rule.last_generated else None,
                }
            )
        return {"recurring": out}

    # ----------------------------------------------------------------- write

    @_tool(write=True, idempotent=False)
    def add_transaction(
        self,
        amount: float | str,
        title: str,
        category_id: int,
        date: str | None = None,
        month: str | None = None,
        note: str = "",
    ) -> dict:
        """Log a spend (or a refund) in the ledger.

        Args:
            amount: positive for money spent, negative for a refund or money paid
                into a fund. A plain number with at most 2 decimal places, e.g.
                12.5 or "12.50", in the ledger's currency (see get_ledger_info);
                no currency symbol or thousands separators.
            title: a short description, e.g. "Weekly groceries".
            category_id: the category's id from list_categories. Archived
                categories take no new transactions.
            date: "YYYY-MM-DD", when it happened; defaults to today.
            month: "YYYY-MM", the month it counts toward; defaults to the date's
                month. Only set it when the spend belongs to another month, e.g.
                May's bill paid on 10 June.
            note: an optional longer note.

        Returns the new transaction, and category_month: where its category
        stands for that month afterwards (budget, spent and left for a budget
        category; top-up, spent and balance for a fund).
        """
        today = self._start()
        amount = _parse_amount(amount)
        title = _clean_title(title)
        category = _get_category(category_id, for_entry=True)
        day = _parse_date(date) if date else today
        counts_toward = _parse_month(month) if month else month_of(day)
        tx = Transaction.objects.create(
            amount=amount,
            title=title,
            category=category,
            date=day,
            month=counts_toward,
            note=(note or "").strip(),
            created_by=self.request.user,
        )
        return {"transaction": _transaction(tx), "category_month": _category_month(category, tx.month)}

    @_tool(write=True, destructive=True)
    def update_transaction(
        self,
        id: int,
        amount: float | str | None = None,
        title: str | None = None,
        category_id: int | None = None,
        date: str | None = None,
        month: str | None = None,
        note: str | None = None,
    ) -> dict:
        """Change an existing transaction. Only the fields you pass change; leave
        the others out.

        Args:
            id: the transaction's id (from list_transactions).
            amount, title, category_id, date, month: as in add_transaction.
            note: the new note; pass "" to clear it.

        If you change date without month, month follows the new date, unless
        the transaction counted toward a different month than its date; then
        that month is kept. Returns the updated transaction, the fields that
        changed, and category_month for its (new) category and month.
        """
        self._start()
        tx = _get_transaction(id)
        changed = []
        if amount is not None:
            tx.amount = _parse_amount(amount)
            changed.append("amount")
        if title is not None:
            tx.title = _clean_title(title)
            changed.append("title")
        if category_id is not None and category_id != tx.category_id:
            tx.category = _get_category(category_id, for_entry=True)
            changed.append("category")
        if date is not None:
            new_date = _parse_date(date)
            if month is None and not tx.counts_elsewhere:
                tx.month = month_of(new_date)
            tx.date = new_date
            changed.append("date")
        if month is not None:
            tx.month = _parse_month(month)
            changed.append("month")
        if note is not None:
            tx.note = note.strip()
            changed.append("note")
        if not changed:
            raise ToolInputError("Nothing to change: pass at least one of amount, title, category_id, date, month, note.")
        tx.save()
        return {
            "transaction": _transaction(tx),
            "changed": changed,
            "category_month": _category_month(tx.category, tx.month),
        }

    @_tool(write=True, destructive=True)
    def delete_transaction(self, id: int) -> dict:
        """Delete a transaction permanently. If a recurring rule created it, the
        rule does not create it again.

        Args:
            id: the transaction's id (from list_transactions).

        Returns the deleted transaction and category_month: where its category
        stands for that month afterwards.
        """
        self._start()
        tx = _get_transaction(id)
        deleted = _transaction(tx)
        tx.delete()
        return {"deleted": deleted, "category_month": _category_month(tx.category, tx.month)}
