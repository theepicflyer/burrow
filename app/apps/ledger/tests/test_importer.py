from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.accounts.models import Account
from apps.budgets.models import Budget
from apps.budgets.services.monthly import _budget_for, monthly_status
from apps.budgets.tasks import materialize_for_month
from apps.common.middleware.thread_local import write_current_user
from apps.currencies.models import Currency
from apps.ledger import importer
from apps.ledger.importer import LedgerNotEmpty, money, run_import
from apps.ledger.models import (
    Category,
    LedgerSettings,
    MonthlyAmount,
    Recurring,
    Transaction,
)
from apps.ledger.months import add_months, month_range
from apps.ledger.services import Book, generate_due
from apps.transactions.models import RecurringTransaction as OldRule
from apps.transactions.models import Transaction as OldTxn
from apps.transactions.models import TransactionCategory as OldCategory

D = Decimal
EX, IN = OldTxn.Type.EXPENSE, OldTxn.Type.INCOME


class OldDataMixin:
    def make_users(self):
        User = get_user_model()
        self.alice = User.objects.create_user(email="alice@example.com", password="pw")
        self.bob = User.objects.create_user(email="bob@example.com", password="pw")
        write_current_user(self.alice)
        self.sgd = Currency.objects.create(code="SGD", name="Singapore Dollar", prefix="S$ ")
        self.main = Account.objects.create(name="Main", currency=self.sgd, owner=self.alice)
        self.pot = Account.objects.create(
            name="Savings pot", currency=self.sgd, kind=Account.Kind.SINKING, owner=self.alice
        )

    def tearDown(self):
        write_current_user(None)

    def txn(self, account, kind, day, amount, category=None, ref=None, desc="", **extra):
        extra.setdefault("owner", account.owner)
        return OldTxn.objects.create(
            account=account,
            type=kind,
            date=day,
            reference_date=ref or day.replace(day=1),
            amount=D(amount),
            category=category,
            description=desc,
            **extra,
        )

    def cat(self, name, account=None, default=None, **extra):
        extra.setdefault("owner", self.alice)
        return OldCategory.objects.create(
            name=name, account=account, monthly_default_amount=default and D(default), **extra
        )

    def rule(self, desc, kind=EX, amount="10", **extra):
        extra.setdefault("account", self.main)
        return OldRule.all_objects.create(description=desc, type=kind, amount=D(amount), **extra)

    def do_import(self, **kwargs):
        # The command runs without a signed-in user; with no user the old
        # visibility managers hide private rows, so this checks the importer
        # reads through the unfiltered ones.
        write_current_user(None)
        return run_import(today=self.today, **kwargs)


@override_settings(HOUSEHOLD_MODE=True)
class ImportWygiwyhTests(OldDataMixin, TestCase):
    today = date(2026, 5, 20)

    def setUp(self):
        self.make_users()
        eur = Currency.objects.create(code="EUR", name="Euro", prefix="€", decimal_places=3)
        card = Account.objects.create(name="Travel card", currency=eur, owner=self.bob)

        self.groceries = self.cat("Groceries", self.main, "400")
        self.bob_groceries = self.cat(" groceries ", owner=self.bob)  # merges into Groceries
        self.dining = self.cat("Dining", self.main)
        self.hobby = self.cat("Old hobby", self.main, "50", active=False)
        self.phone = self.cat("Phone", self.main, "40")
        salary = self.cat("Salary", self.main)
        self.holiday = self.cat("Holiday", self.pot, "50")

        Budget.all_objects.create(category=self.groceries, month=date(2026, 1, 1), amount=D("300"), owner=self.alice)
        Budget.all_objects.create(category=self.groceries, month=date(2026, 2, 1), amount=D("450"), owner=self.alice)
        Budget.all_objects.create(category=self.dining, month=date(2026, 3, 1), amount=D("100"), owner=self.alice)

        # Monthly allocations as the old task made them: 50 in Jan and Feb, 80 in
        # Mar and May, none in Apr; the default is 100 from now on.
        materialize_for_month(date(2026, 1, 1))
        materialize_for_month(date(2026, 2, 1))
        self.holiday.monthly_default_amount = D("80")
        self.holiday.save()
        materialize_for_month(date(2026, 3, 1))
        materialize_for_month(date(2026, 5, 1))
        self.holiday.monthly_default_amount = D("100")
        self.holiday.save()

        self.txn(self.main, EX, date(2026, 1, 10), "120.50", self.groceries, desc="Weekly shop")
        self.txn(self.main, EX, date(2026, 2, 5), "200", self.groceries)  # no description
        self.txn(self.main, IN, date(2026, 2, 14), "15", self.groceries, desc="Returned eggs")
        self.txn(card, EX, date(2026, 3, 20), "12.345", self.bob_groceries, desc="Market")
        self.txn(self.main, EX, date(2026, 3, 12), "45", self.dining, desc="Dinner out", mute=True)
        self.txn(self.main, EX, date(2026, 3, 3), "25", desc="Parking")
        self.txn(self.main, EX, date(2026, 4, 2), "30", desc="To holiday pot")
        self.txn(self.pot, IN, date(2026, 4, 2), "30", self.holiday, desc="From main")
        self.txn(self.pot, EX, date(2026, 3, 10), "120", self.holiday, desc="Flights")
        self.txn(self.main, IN, date(2026, 1, 25), "3000", desc="Salary")
        self.txn(self.main, IN, date(2026, 2, 25), "3000", salary, desc="Pay")
        self.txn(self.main, EX, date(2026, 6, 3), "80", self.groceries, desc="Planned", is_paid=False)
        self.txn(self.main, EX, date(2026, 3, 15), "999", self.groceries, desc="Typo", deleted=True)

        # Phone bill: billed on the 8th, counts toward the previous month.
        phone_rule = self.rule(
            "Phone bill", amount="40", category=self.phone, start_date=date(2026, 1, 8),
            reference_date=date(2025, 12, 8), recurrence_type="month", recurrence_interval=1,
        )
        for month in range(1, 7):
            self.txn(
                self.main, EX, date(2026, month, 8), "40", self.phone, desc="Phone bill",
                ref=add_months(date(2026, month, 1), -1),
                recurring_transaction=phone_rule, is_paid=month < 6,
            )
        self.rule("Cleaner", amount="60", start_date=date(2026, 5, 1), recurrence_type="day", recurrence_interval=14)
        self.rule("Newspaper", amount="2", start_date=date(2026, 1, 1), recurrence_type="day", recurrence_interval=1)
        self.rule("Pay", kind=IN, amount="3000", start_date=date(2026, 1, 25), recurrence_type="month",
                  recurrence_interval=1)
        self.rule("Gym", amount="30", start_date=date(2026, 1, 1), end_date=date(2026, 2, 28),
                  recurrence_type="month", recurrence_interval=1)

    def test_categories(self):
        report = self.do_import()
        budgets = dict(Category.objects.filter(kind=Category.Kind.BUDGET).values_list("name", "archived"))
        self.assertEqual(
            budgets,
            {"Dining": False, "Groceries": False, "Old hobby": True, "Phone": False, "Uncategorized": False},
        )
        self.assertEqual(list(Category.objects.filter(kind=Category.Kind.FUND).values_list("name", flat=True)),
                         ["Holiday"])
        self.assertEqual(report.not_created, ["Salary"])
        self.assertIn("Groceries (merged 2)", report.budgets)

    def test_budget_history_reproduces_old_budgets(self):
        self.do_import()
        old = {
            "Groceries": [self.groceries, self.bob_groceries],
            "Dining": [self.dining],
            "Old hobby": [self.hobby],
            "Phone": [self.phone],
        }
        for name, cats in old.items():
            new = Category.objects.get(name=name)
            for m in month_range(date(2025, 11, 1), date(2026, 9, 1)):
                values = [v for v in (_budget_for(c, m) for c in cats) if v is not None]
                expected = money(sum(values)) if values and m >= date(2025, 12, 1) else D("0")
                self.assertEqual(new.amount_for(m), expected, f"{name} {m}")

        def rows(name):
            return list(MonthlyAmount.objects.filter(category__name=name).values_list("start_month", "amount"))

        self.assertEqual(rows("Groceries"), [
            (date(2025, 12, 1), D("400")), (date(2026, 1, 1), D("300")),
            (date(2026, 2, 1), D("450")), (date(2026, 3, 1), D("400")),
        ])
        self.assertEqual(rows("Dining"), [(date(2026, 3, 1), D("100")), (date(2026, 4, 1), D("0"))])
        self.assertEqual(rows("Uncategorized"), [])

    def test_fund_balance_matches_old_balance_every_month(self):
        report = self.do_import()
        fund = Category.objects.get(name="Holiday")
        self.assertEqual(
            list(fund.amounts.values_list("start_month", "amount")),
            [(date(2026, 1, 1), D("50")), (date(2026, 3, 1), D("80")), (date(2026, 4, 1), D("0")),
             (date(2026, 5, 1), D("80")), (date(2026, 6, 1), D("100"))],
        )
        book = Book()
        write_current_user(self.alice)
        for m in month_range(date(2025, 12, 1), self.today):
            row = next(r for r in monthly_status(self.alice, m.year, m.month) if r.category == self.holiday)
            self.assertEqual(book.fund_balance(fund, m), money(row.balance), m)
        self.assertEqual(report.fund_balances, [("Holiday", D("170.00"), D("170.00"))])
        self.assertTrue(report.balances_match)

    def test_transactions(self):
        report = self.do_import()
        self.assertEqual(dict(report.imported), {
            importer.SPEND: 9, importer.REFUND: 1, importer.UNCAT_SPEND: 2,
            importer.FUND_SPEND: 1, importer.FUND_DEPOSIT: 1,
        })
        self.assertEqual(report.muted, 1)
        self.assertEqual(Transaction.objects.count(), 14)
        self.assertFalse(Transaction.objects.filter(title__startswith="[auto-allocation]").exists())

        market = Transaction.objects.get(title="Market")
        self.assertEqual((market.amount, market.category.name, market.created_by), (D("12.35"), "Groceries", self.bob))
        self.assertEqual(Transaction.objects.get(date=date(2026, 2, 5)).title, "Groceries")
        self.assertEqual(Transaction.objects.get(title="Returned eggs").amount, D("-15.00"))
        self.assertEqual(Transaction.objects.get(title="From main").amount, D("-30.00"))
        self.assertEqual(Transaction.objects.get(title="Flights").amount, D("120.00"))
        self.assertEqual(Transaction.objects.get(title="Parking").category.name, "Uncategorized")
        bill = Transaction.objects.get(title="Phone bill", date=date(2026, 3, 8))
        self.assertEqual(bill.month, date(2026, 2, 1))
        self.assertTrue(any("may be transfers" in n for n in report.notes))

    def test_skips_are_counted(self):
        report = self.do_import()
        self.assertEqual(dict(report.skipped), {
            importer.SKIP_DELETED: 1,
            importer.SKIP_ALLOCATION: 8,
            importer.SKIP_UNPAID_FUTURE: 2,
            importer.SKIP_INCOME: 1,
            importer.SKIP_INCOME_CATEGORY: 1,
        })
        self.assertEqual([line.split(":")[0] for line in report.rules_skipped], ["Newspaper", "Pay", "Gym"])

    def test_recurring_rules(self):
        report = self.do_import()
        phone = Recurring.objects.get(title="Phone bill")
        self.assertEqual(
            (phone.unit, phone.every, phone.month_offset, phone.last_generated, phone.category.name),
            (Recurring.Unit.MONTH, 1, -1, date(2026, 5, 8), "Phone"),
        )
        self.assertEqual(phone.transactions.count(), 5)
        cleaner = Recurring.objects.get(title="Cleaner")
        self.assertEqual(
            (cleaner.unit, cleaner.every, cleaner.last_generated, cleaner.category.name),
            (Recurring.Unit.WEEK, 2, self.today, "Uncategorized"),
        )
        self.assertEqual(report.linked, 5)
        self.assertEqual(generate_due(today=self.today), 0)  # nothing is backfilled

    def test_currency(self):
        report = self.do_import()
        self.assertEqual(LedgerSettings.load().currency, "S$")
        self.assertEqual(report.other_currencies, [("EUR", 1)])

    @override_settings(HOUSEHOLD_MODE=False)
    def test_imports_every_users_data_whoever_is_signed_in(self):
        write_current_user(self.bob)
        report = run_import(today=self.today)
        self.assertEqual(Transaction.objects.count(), 14)
        self.assertEqual(report.fund_balances, [("Holiday", D("170.00"), D("170.00"))])

    def test_refuses_a_ledger_with_data_unless_replace(self):
        self.do_import()
        with self.assertRaises(LedgerNotEmpty):
            self.do_import()
        with self.assertRaises(CommandError):
            call_command("import_wygiwyh", stdout=StringIO())
        report = self.do_import(replace=True)
        self.assertEqual(report.replaced["transactions"], 14)
        self.assertEqual(Transaction.objects.count(), 14)
        self.assertEqual(Category.objects.count(), 6)
        self.assertEqual(Recurring.objects.count(), 2)

    def test_dry_run_leaves_nothing(self):
        out = StringIO()
        write_current_user(None)
        call_command("import_wygiwyh", "--dry-run", stdout=out)
        for model in (Category, MonthlyAmount, Transaction, Recurring):
            self.assertFalse(model.objects.exists(), model)
        self.assertEqual(LedgerSettings.load().currency, "$")
        text = out.getvalue()
        self.assertIn("dry run", text)
        self.assertIn("Transactions imported: 14", text)
        self.assertIn("Holiday", text)


@override_settings(HOUSEHOLD_MODE=True)
class FundAndRuleEdgeCaseTests(OldDataMixin, TestCase):
    today = date(2026, 4, 10)

    def setUp(self):
        self.make_users()
        self.bike = self.cat("Bike", self.pot, "20")
        for month in (1, 2, 3):
            materialize_for_month(date(2026, month, 1))
        self.bike.active = False  # retired: the old task stopped allocating it
        self.bike.save()
        self.cat("Car", self.pot, "25")  # set up after this month's allocation ran

        rent = self.cat("Rent", self.main, "1500")
        rule = self.rule("Rent", amount="1500", category=rent, start_date=date(2026, 1, 31),
                         recurrence_type="month", recurrence_interval=1)
        # The old engine added a month at a time, so the 31st drifted to the 28th.
        for day in (date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 28)):
            self.txn(self.main, EX, day, "1500", rent, desc="Rent", recurring_transaction=rule)

    def test_archived_fund_stops_and_unallocated_fund_starts_now(self):
        report = self.do_import()
        bike, car = Category.objects.get(name="Bike"), Category.objects.get(name="Car")
        self.assertTrue(bike.archived)
        self.assertEqual(list(bike.amounts.values_list("start_month", "amount")),
                         [(date(2026, 1, 1), D("20")), (date(2026, 4, 1), D("0"))])
        self.assertEqual(list(car.amounts.values_list("start_month", "amount")), [(date(2026, 4, 1), D("25"))])
        self.assertEqual(report.fund_balances, [("Bike", D("60.00"), D("60")), ("Car", D("0.00"), D("25"))])
        self.assertFalse(report.balances_match)
        self.assertTrue(any("'Car': never allocated" in n for n in report.notes))
        self.assertIn("DIFFERS", report.render())

    def test_drifted_monthly_rule_does_not_repeat_this_month(self):
        self.do_import()
        rule = Recurring.objects.get(title="Rent")
        self.assertEqual(rule.last_generated, date(2026, 3, 31))
        self.assertEqual(generate_due(today=self.today), 0)
        self.assertEqual(rule.next_date(), date(2026, 4, 30))
