"""Import the old WYGIWYH data into the household ledger.

``run_import()`` does the work and returns an ``ImportReport``; the
``import_wygiwyh`` management command is a thin wrapper around it.

The mapping, in short:

* One ledger ``Category`` per old category name (case-insensitive, merged across
  owners). Categories on a sinking account become funds; a category that only
  ever saw income (salary, interest) and has no budget becomes an income
  category; the rest are budgets. Inactive ones are archived. Names are unique
  across kinds: a budget keeps its name, a clashing fund or income category
  gets " (fund)" or " (income)".
* Budgets: the old effective budget (explicit ``Budget`` row, else the
  category's default) is replayed month by month into effective-dated
  ``MonthlyAmount`` rows, written only where the amount changes.
* Funds: the ``[auto-allocation]`` pairs are dropped. Each month's allocation
  becomes the fund's top-up (0 in months without one), and the old default
  takes over after the last allocation if the old monthly task would still
  have allocated it (active category, unarchived sinking account).
* Transactions keep their type (expense or income) with a positive amount.
  Income in a budget or fund category is money back or money into the fund.
  Uncategorized expenses go to "Uncategorized", uncategorized income to
  "Other income" (an income category). Unpaid (planned) transactions and zero
  amounts are skipped. Transfers between accounts carry no marker, so both legs
  are imported and likely pairs are listed in the report.
* Unfinished ``RecurringTransaction`` rules (expense and income) become
  ``Recurring`` rules that pick up after the last imported (paid) entry.

Old data is read through the unfiltered managers, so the import sees every
user's data whatever the thread-local user is.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction as db_transaction
from django.db.models import Case, DecimalField, F, Sum, When
from django.utils import timezone

from apps.accounts.models import Account
from apps.budgets.models import Budget
from apps.ledger.models import (
    Category,
    MonthlyAmount,
    Recurring,
    Transaction,
)
from apps.ledger.months import add_months, month_of, month_range
from apps.ledger.services import Book
from apps.transactions.models import RecurringTransaction as OldRule
from apps.transactions.models import Transaction as OldTxn
from apps.transactions.models import TransactionCategory as OldCategory

ALLOCATION_MARKER = "[auto-allocation]"
UNCATEGORIZED = "Uncategorized"
OTHER_INCOME = "Other income"
CENT = Decimal("0.01")
ZERO = Decimal(0)

# Labels used in the report (and by the tests), expenses then income.
SPEND, UNCAT_SPEND = "spends in budgets", f"uncategorized spends, to '{UNCATEGORIZED}'"
FUND_SPEND, INCOME_SPEND = "spends from funds", "spends in income categories"
INCOME, UNCAT_INCOME = "income in income categories", f"uncategorized income, to '{OTHER_INCOME}'"
REFUND, FUND_DEPOSIT = "money back in budgets", "money into funds"
EXPENSE_LABELS = (SPEND, UNCAT_SPEND, FUND_SPEND, INCOME_SPEND)
INCOME_LABELS = (INCOME, UNCAT_INCOME, REFUND, FUND_DEPOSIT)
SKIP_ALLOCATION = "auto-allocation legs (now fund top-ups)"
SKIP_UNPAID_FUTURE = "unpaid (planned), dated after today"
SKIP_UNPAID_PAST = "unpaid, dated today or earlier"
SKIP_ZERO = "zero amount"
SKIP_DELETED = "soft-deleted"

# For names used by more than one kind: the article form, the noun, the suffix.
_A_KIND = {Category.Kind.BUDGET: "a budget", Category.Kind.FUND: "a fund", Category.Kind.INCOME: "an income category"}
_SUFFIX = {Category.Kind.FUND: " (fund)", Category.Kind.INCOME: " (income)"}


class LedgerNotEmpty(Exception):
    pass


def money(value) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _months_apart(a: date, b: date) -> int:
    """``b``'s month minus ``a``'s month."""
    return (b.year - a.year) * 12 + b.month - a.month


def old_fund_balance(category_ids, month: date) -> Decimal:
    """End-of-month fund balance the way the old Budget tab computed it
    (``budgets.services.monthly.monthly_status``): the signed total dated before
    the month (carryover), plus received minus spent counted toward the month."""
    signed = Case(
        When(type=OldTxn.Type.INCOME, then=F("amount")),
        default=-F("amount"),
        output_field=DecimalField(max_digits=42, decimal_places=30),
    )
    qs = OldTxn.userless_all_objects.filter(deleted=False, category_id__in=list(category_ids))
    carry = qs.filter(date__lt=month).aggregate(t=Sum(signed))["t"] or ZERO
    this = qs.filter(reference_date__year=month.year, reference_date__month=month.month)
    return carry + (this.aggregate(t=Sum(signed))["t"] or ZERO)


@dataclass
class ImportReport:
    today: date
    dry_run: bool = False
    replaced: dict = field(default_factory=dict)
    budgets: list = field(default_factory=list)
    funds: list = field(default_factory=list)
    incomes: list = field(default_factory=list)
    monthly_amounts: int = 0
    imported: Counter = field(default_factory=Counter)  # by label, see EXPENSE_LABELS and INCOME_LABELS
    muted: int = 0
    skipped: Counter = field(default_factory=Counter)
    rules: list = field(default_factory=list)
    rules_skipped: list = field(default_factory=list)
    linked: int = 0
    currency: str = ""
    other_currencies: list = field(default_factory=list)
    fund_balances: list = field(default_factory=list)  # (name, old, new)
    notes: list = field(default_factory=list)

    @property
    def balances_match(self) -> bool:
        return all(old == new for _name, old, new in self.fund_balances)

    def render(self) -> str:
        out = []
        add = out.append
        add("WYGIWYH import" + (" (dry run: nothing was saved)" if self.dry_run else ""))
        if self.replaced:
            add("Replaced the existing ledger: " + ", ".join(f"{n} {what}" for what, n in self.replaced.items()))
        add("")
        add(f"Categories ({self.monthly_amounts} monthly amounts written)")
        add(f"  Budgets ({len(self.budgets)}): " + (", ".join(self.budgets) or "none"))
        add(f"  Funds ({len(self.funds)}): " + (", ".join(self.funds) or "none"))
        add(f"  Income ({len(self.incomes)}): " + (", ".join(self.incomes) or "none"))
        add("")
        add(f"Transactions imported: {sum(self.imported.values())}")
        for heading, labels in (("Expenses", EXPENSE_LABELS), ("Income", INCOME_LABELS)):
            add(f"  {heading + ':':<52}{sum(self.imported[label] for label in labels):>7}")
            for label in labels:
                if self.imported[label]:
                    add(f"    {label:<50}{self.imported[label]:>7}")
        add(f"  {'(muted in the old app, kept)':<52}{self.muted:>7}")
        add(f"Transactions skipped: {sum(self.skipped.values())}")
        for label, n in self.skipped.items():
            add(f"  {label:<52}{n:>7}")
        add("")
        add(f"Recurring rules imported: {len(self.rules)} ({self.linked} transactions linked)")
        for line in self.rules:
            add(f"  {line}")
        if self.rules_skipped:
            add(f"Recurring rules skipped: {len(self.rules_skipped)}")
            for line in self.rules_skipped:
                add(f"  {line}")
        add("")
        add("Currency: " + (f"{self.currency}; Burrow shows every amount with $" if self.currency else "none"))
        if self.other_currencies:
            add("  Also used, amounts imported as is (not converted): "
                + ", ".join(f"{code} ({n} transactions)" for code, n in self.other_currencies))
        add("")
        add(f"Fund balances at the end of {month_of(self.today):%Y-%m}:")
        if not self.fund_balances:
            add("  no funds")
        for name, old, new in self.fund_balances:
            add(f"  {name:<30} old {old:>12}  new {new:>12}  {'ok' if old == new else 'DIFFERS'}")
        if self.notes:
            add("")
            add("Notes:")
            for note in self.notes:
                add(f"  - {note}")
        return "\n".join(out)


@dataclass(eq=False)
class _Group:
    """The old categories that become one ledger category."""

    name: str
    kind: str
    old: list = field(default_factory=list)
    spends: int = 0  # expense activity: transactions (paid or not) and expense rules
    incomes: int = 0  # income activity, likewise
    category: Category | None = None

    @property
    def is_fund(self) -> bool:
        return self.kind == Category.Kind.FUND

    @property
    def is_income(self) -> bool:
        return self.kind == Category.Kind.INCOME


def run_import(*, replace: bool = False, dry_run: bool = False, today: date | None = None) -> ImportReport:
    """Import everything in one transaction. Refuses to touch a ledger that has
    data unless ``replace``; ``dry_run`` rolls everything back."""
    today = today or timezone.localdate()
    with db_transaction.atomic():
        replaced = {}
        if Category.objects.exists() or Transaction.objects.exists():
            if not replace:
                raise LedgerNotEmpty(
                    "The ledger already has categories or transactions. "
                    "Pass --replace to delete them and import again."
                )
            replaced = {
                "transactions": Transaction.objects.all().delete()[0],
                "recurring rules": Recurring.objects.all().delete()[0],
                "monthly amounts": MonthlyAmount.objects.all().delete()[0],
                "categories": Category.objects.all().delete()[0],
            }
        report = _Importer(today).run()
        report.replaced = replaced
        report.dry_run = dry_run
        if dry_run:
            db_transaction.set_rollback(True)
    return report


class _Importer:
    def __init__(self, today: date):
        self.today = today
        self.current = month_of(today)
        self.report = ImportReport(today=today)
        self.groups: dict[tuple[str, str], _Group] = {}
        self.group_of: dict[int, _Group] = {}  # old category id -> group
        self.explicit: dict[tuple[int, date], Decimal] = {}  # old Budget rows
        self.pending: list[tuple[OldTxn, _Group]] = []  # transactions to import
        self.allocations: dict[_Group, dict[date, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        self.rule_offsets: dict[int, set[int]] = defaultdict(set)  # old rule id -> month offsets seen
        self.rules: dict[int, Recurring] = {}  # old rule id -> new rule

    def run(self) -> ImportReport:
        self._load_categories()
        self._scan_transactions()
        rules = self._scan_rules()
        self._create_categories()
        self._budget_amounts()
        self._fund_amounts()
        self._create_rules(rules)
        self._create_transactions()
        self._flag_transfers()
        self._currencies()
        self._check_funds()
        return self.report

    # ------------------------------------------------------------------ reading

    def _load_categories(self):
        for old in OldCategory.all_objects.select_related("account").order_by("id"):
            sinking = old.account is not None and old.account.kind == Account.Kind.SINKING
            kind = Category.Kind.FUND if sinking else Category.Kind.BUDGET
            name = " ".join(old.name.split())[:80] or "Unnamed"
            group = self.groups.setdefault((name.casefold(), kind), _Group(name, kind))
            group.old.append(old)
            self.group_of[old.id] = group
        for b in Budget.all_objects.all():
            self.explicit[(b.category_id, month_of(b.month))] = b.amount

    def _uncategorized(self, expense: bool = True) -> _Group:
        """Where uncategorized expenses ("Uncategorized") or income ("Other income") go.
        An old income-only "Other income" category is joined in ``_create_categories``."""
        name, kind = (UNCATEGORIZED, Category.Kind.BUDGET) if expense else (OTHER_INCOME, Category.Kind.INCOME)
        return self.groups.setdefault((name.casefold(), kind), _Group(name, kind))

    def _scan_transactions(self):
        skip = self.report.skipped
        if n := OldTxn.userless_all_objects.filter(deleted=True).count():
            skip[SKIP_DELETED] = n
        qs = OldTxn.userless_all_objects.filter(deleted=False).select_related("account__currency")
        for t in qs.order_by("date", "id"):
            group = self.group_of.get(t.category_id)
            expense = t.type == OldTxn.Type.EXPENSE
            if t.description.startswith(ALLOCATION_MARKER):
                if not expense and group is not None and group.is_fund:
                    self.allocations[group][month_of(t.reference_date)] += t.amount
                skip[SKIP_ALLOCATION] += 1
                continue
            if t.recurring_transaction_id:
                self.rule_offsets[t.recurring_transaction_id].add(_months_apart(t.date, t.reference_date))
            if group is not None:
                if expense:
                    group.spends += 1
                else:
                    group.incomes += 1
            if not t.is_paid:
                skip[SKIP_UNPAID_FUTURE if t.date > self.today else SKIP_UNPAID_PAST] += 1
                continue
            if money(t.amount) <= 0:
                skip[SKIP_ZERO] += 1
                continue
            if group is None:
                group = self._uncategorized(expense)
                if expense:
                    group.spends += 1
                else:
                    group.incomes += 1
            self.pending.append((t, group))

    def _scan_rules(self) -> list:
        keep = []
        for rule in OldRule.all_objects.select_related("account").order_by("id"):
            name = rule.description or f"rule #{rule.id}"
            reason = None
            unit, every = self._schedule(rule)
            if rule.end_date and rule.end_date < self.today:
                reason = f"finished on {rule.end_date}"
            elif unit is None:
                reason = (
                    f"every {rule.recurrence_interval} {rule.recurrence_type}(s) cannot be "
                    f"expressed in whole weeks, months or years"
                )
            elif money(rule.amount) <= 0:
                reason = "amount is 0"
            if reason:
                self.report.rules_skipped.append(f"{name}: {reason}")
                continue
            expense = rule.type == OldTxn.Type.EXPENSE
            group = self.group_of.get(rule.category_id) or self._uncategorized(expense)
            if expense:
                group.spends += 1
            else:
                group.incomes += 1
            keep.append((rule, group, unit, every))
        return keep

    @staticmethod
    def _schedule(rule: OldRule) -> tuple[str | None, int | None]:
        n, kind = rule.recurrence_interval, rule.recurrence_type
        if n < 1:
            return None, None
        if kind == OldRule.RecurrenceType.DAY:
            return (Recurring.Unit.WEEK, n // 7) if n % 7 == 0 else (None, None)
        units = {
            OldRule.RecurrenceType.WEEK: Recurring.Unit.WEEK,
            OldRule.RecurrenceType.MONTH: Recurring.Unit.MONTH,
            OldRule.RecurrenceType.YEAR: Recurring.Unit.YEAR,
        }
        return units[kind], n

    # ------------------------------------------------------------------ writing

    def _create_categories(self):
        r = self.report
        budgeted = {cat_id for cat_id, _m in self.explicit}
        for group in self.groups.values():
            has_budget = any(c.monthly_default_amount is not None or c.id in budgeted for c in group.old)
            only_income = group.old and group.incomes and not group.spends and not has_budget
            if group.kind == Category.Kind.BUDGET and only_income:
                group.kind = Category.Kind.INCOME
        labels = {Category.Kind.BUDGET: r.budgets, Category.Kind.FUND: r.funds, Category.Kind.INCOME: r.incomes}
        made: dict[tuple[str, str], Category] = {}
        taken: dict[str, str] = {}  # casefolded name -> kind that has it
        # Kinds sort budget, fund, income, so a budget keeps its name, then a fund. An
        # old category sorts before the "Other income" group, which then joins it.
        for group in sorted(self.groups.values(), key=lambda g: (g.kind, g.name.casefold(), not g.old)):
            key = (group.name.casefold(), group.kind)
            if key in made:
                group.category = made[key]
                continue
            name = group.name
            if other := taken.get(name.casefold()):
                suffix = _SUFFIX[group.kind]
                name = name[: 80 - len(suffix)] + suffix
                r.notes.append(
                    f"'{group.name}' is both {_A_KIND[other]} and {_A_KIND[group.kind]} in the old data; "
                    f"the {_A_KIND[group.kind].split(' ', 1)[1]} is now '{name}'."
                )
            taken[name.casefold()] = group.kind
            archived = bool(group.old) and not any(c.active for c in group.old)
            group.category = made[key] = Category.objects.create(name=name, kind=group.kind, archived=archived)
            label = name + (" (archived)" if archived else "")
            if len(group.old) > 1:
                label += f" (merged {len(group.old)})"
            labels[group.kind].append(label)

    def _old_budget(self, group: _Group, m: date) -> Decimal | None:
        """The old effective budget for ``m`` (``_budget_for``), summed over merged categories."""
        values = [self.explicit.get((c.id, m), c.monthly_default_amount) for c in group.old]
        values = [v for v in values if v is not None]
        return sum(values, ZERO) if values else None

    def _budget_amounts(self):
        groups = [g for g in self.groups.values() if g.kind == Category.Kind.BUDGET and g.old]
        old_ids = {c.id for g in groups for c in g.old}
        budget_months = [m for cat_id, m in self.explicit if cat_id in old_ids]
        # Income categories don't open the range: budgets start with the spending data.
        txn_months = [month_of(t.reference_date) for t, g in self.pending if not g.is_income]
        first = min(budget_months + txn_months, default=self.current)
        # One month past the last explicit row so the current default carries on.
        last = add_months(max(budget_months + [self.current]), 1)
        months = month_range(first, last)
        rows = []
        for group in groups:
            prev = None
            for m in months:
                value = self._old_budget(group, m)
                if value is None:
                    if not prev:  # no row yet, or already 0
                        continue
                    value = ZERO
                value = money(value)
                if value != prev:
                    rows.append(MonthlyAmount(category=group.category, start_month=m, amount=value))
                    prev = value
        MonthlyAmount.objects.bulk_create(rows)
        self.report.monthly_amounts += len(rows)

    def _fund_amounts(self):
        rows = []
        for group in self.groups.values():
            if not group.is_fund:
                continue
            allocs = self.allocations.get(group, {})
            prev = None
            for m in month_range(min(allocs), max(allocs)) if allocs else []:
                value = money(allocs.get(m, ZERO))
                if value != prev:
                    rows.append(MonthlyAmount(category=group.category, start_month=m, amount=value))
                    prev = value
            after = add_months(max(allocs), 1) if allocs else self.current
            # The old monthly task only allocated active categories on unarchived accounts.
            default = money(sum(
                (c.monthly_default_amount for c in group.old
                 if c.active and not c.account.is_archived and c.monthly_default_amount),
                ZERO,
            ))
            value = default if default > 0 else (ZERO if prev else None)
            if value is not None and value != prev:
                rows.append(MonthlyAmount(category=group.category, start_month=after, amount=value))
            if default > 0 and after <= self.current:
                since = f"no allocation since {max(allocs):%Y-%m}" if allocs else "never allocated"
                n = _months_apart(after, self.current) + 1
                self.report.notes.append(
                    f"Fund '{group.category.name}': {since} in the old app; its default {default} now tops it up "
                    f"from {after:%Y-%m}, so it is {default * n} above the old balance."
                )
            elif not default and any(c.monthly_default_amount for c in group.old):
                self.report.notes.append(
                    f"Fund '{group.category.name}' is inactive or on an archived account, so its old default "
                    f"top-up is not carried forward."
                )
        MonthlyAmount.objects.bulk_create(rows)
        self.report.monthly_amounts += len(rows)

    def _create_rules(self, rules: list):
        latest: dict[int, date] = {}
        for t, _group in self.pending:
            if t.recurring_transaction_id:
                latest[t.recurring_transaction_id] = max(t.date, latest.get(t.recurring_transaction_id, t.date))
        for old, group, unit, every in rules:
            offsets = set(self.rule_offsets.get(old.id, set()))
            if old.reference_date:
                offsets.add(_months_apart(old.start_date, old.reference_date))
            rule = Recurring(
                type=Recurring.Type.EXPENSE if old.type == OldTxn.Type.EXPENSE else Recurring.Type.INCOME,
                title=(old.description.strip() or group.category.name)[:200],
                amount=money(old.amount),
                category=group.category,
                note=old.notes,
                every=every,
                unit=unit,
                start_date=old.start_date,
                end_date=old.end_date,
                month_offset=-1 if offsets == {-1} else 0,
                paused=old.is_paused,
                created_by=old.account.owner,
            )
            last = latest.get(old.id)
            rule.last_generated = self._snap(rule, last) if last else self.today
            rule.save()
            self.rules[old.id] = rule

            line = f"{rule.title}: {rule.frequency_label}"
            if rule.type == Recurring.Type.INCOME:
                line += ", income"
            if rule.month_offset:
                line += ", counts toward the previous month"
            if rule.paused:
                line += ", paused"
            nxt = rule.next_date()
            line += f", next {nxt}" if nxt else ", ended"
            self.report.rules.append(line)
            if old.recurrence_type == OldRule.RecurrenceType.DAY:
                self.report.notes.append(
                    f"Rule '{rule.title}': every {old.recurrence_interval} days became "
                    f"{str(rule.frequency_label).lower()}."
                )
            if offsets - {0, -1} or len(offsets) > 1:
                self.report.notes.append(
                    f"Rule '{rule.title}': its entries count toward differing months "
                    f"(offsets {sorted(offsets)}); set to the same month."
                )
            if not rule.paused and (due := rule.dates_between(rule.last_generated, self.today)):
                self.report.notes.append(
                    f"Rule '{rule.title}': the next recurring run creates {len(due)} entries "
                    f"({due[0]} to {due[-1]}) that have no paid entry in the old app."
                )

    @staticmethod
    def _snap(rule: Recurring, last: date) -> date:
        """The old engine let a monthly rule's day drift (31 Jan, 28 Feb, 28 Mar)
        and people move entries within the month. For monthly and yearly rules,
        treat the new schedule's date in ``last``'s month as generated so the next
        run does not create that month's entry again."""
        if rule.unit == Recurring.Unit.WEEK:
            return last
        snapped, n = last, 0
        while month_of(d := rule.occurrence(n)) <= month_of(last):
            snapped, n = d, n + 1
        return max(snapped, last)

    def _create_transactions(self):
        r = self.report
        objs, rounded = [], 0
        net: dict[_Group, Decimal] = defaultdict(Decimal)
        for t, group in self.pending:
            expense = t.type == OldTxn.Type.EXPENSE
            amount = money(t.amount)
            rounded += amount != t.amount
            net[group] += amount if expense else -amount
            if t.category_id is None:
                label = UNCAT_SPEND if expense else UNCAT_INCOME
            elif group.is_fund:
                label = FUND_SPEND if expense else FUND_DEPOSIT
            elif group.is_income:
                label = INCOME_SPEND if expense else INCOME
            else:
                label = SPEND if expense else REFUND
            r.imported[label] += 1
            r.muted += t.mute
            rule = self.rules.get(t.recurring_transaction_id)
            r.linked += rule is not None
            objs.append(
                Transaction(
                    type=Transaction.Type.EXPENSE if expense else Transaction.Type.INCOME,
                    amount=amount,
                    title=(t.description.strip() or group.category.name)[:200],
                    category=group.category,
                    date=t.date,
                    month=month_of(t.reference_date or t.date),
                    note=t.notes,
                    recurring=rule,
                    created_by_id=t.owner_id,
                )
            )
        Transaction.objects.bulk_create(objs, batch_size=1000)

        if rounded:
            r.notes.append(f"{rounded} amounts had more than 2 decimal places and were rounded to cents.")
        if n := r.skipped.get(SKIP_UNPAID_PAST):
            r.notes.append(
                f"{n} unpaid transactions dated today or earlier were skipped. If they happened, mark them "
                f"paid in the old app and import again with --replace."
            )
        for group, total in net.items():
            if group.kind == Category.Kind.BUDGET and total < 0:
                r.notes.append(
                    f"Budget '{group.category.name}' has more income than spending ({total}); "
                    f"check whether it is an income category."
                )

    def _flag_transfers(self):
        """The old app recorded a transfer between accounts as an expense on one and
        an income on the other, with no marker, so both legs were imported. Pair an
        imported expense with an imported income of the same amount on the same day
        on another account, one of the two uncategorized, and list the pairs."""
        incomes = defaultdict(list)
        for t, group in self.pending:
            if t.type == OldTxn.Type.INCOME:
                incomes[(t.date, t.amount)].append((t, group))
        pairs, total, out_legs, in_legs = 0, ZERO, Counter(), Counter()
        for t, group in self.pending:
            if t.type != OldTxn.Type.EXPENSE:
                continue
            candidates = incomes.get((t.date, t.amount), [])
            for i, (u, u_group) in enumerate(candidates):
                if u.account_id != t.account_id and (t.category_id is None or u.category_id is None):
                    del candidates[i]
                    pairs += 1
                    total += money(t.amount)
                    out_legs[group.category.name] += 1
                    in_legs[u_group.category.name] += 1
                    break
        if pairs:
            out_in = [", ".join(f"'{name}' ({n})" for name, n in sorted(legs.items())) for legs in (out_legs, in_legs)]
            self.report.notes.append(
                f"{pairs} possible transfers between accounts (total {total}): an expense and an income of the "
                f"same amount on the same day on different accounts, at least one of them uncategorized. Both "
                f"legs were imported: the expenses in {out_in[0]}, the income in {out_in[1]}. Where one is a "
                f"transfer, delete the legs that are not real spending, income or money into a fund."
            )

    def _currencies(self):
        """Amounts are imported as they are, in whatever currency; nothing is stored."""
        counts = Counter(t.account.currency.code for t, _g in self.pending)
        if counts:
            (top, n), *others = counts.most_common()
            self.report.currency = f"{top} ({n} transactions)"
            self.report.other_currencies = others

    def _check_funds(self):
        book = Book()
        for group in self.groups.values():
            if group.is_fund:
                old = money(old_fund_balance([c.id for c in group.old], self.current))
                new = book.fund_balance(group.category, self.current)
                self.report.fund_balances.append((group.category.name, old, new))
        self.report.fund_balances.sort()
        if not self.report.balances_match:
            self.report.notes.append(
                "A fund balance differs. Besides any top-up notes above, the old balance also counts unpaid "
                "transactions, and it counts a transaction dated in a different month from the one it counts "
                "toward in neither or both of those months."
            )
