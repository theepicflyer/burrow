from datetime import date
from decimal import Decimal as D

from django.test import TestCase

from apps.ledger import services
from apps.ledger.models import Category, Recurring, Transaction


def spend(cat, amount, d, month=None, title="Spend"):
    return Transaction.objects.create(category=cat, amount=D(amount), date=d, month=month or d, title=title)


class MonthlyAmountTests(TestCase):
    def test_changing_the_amount_keeps_earlier_months(self):
        cat = Category.objects.create(name="Groceries")
        cat.set_amount(D("500"), date(2026, 1, 1))
        cat.set_amount(D("650"), date(2026, 6, 15))
        self.assertEqual(cat.amount_for(date(2025, 12, 1)), D("0"))
        self.assertEqual(cat.amount_for(date(2026, 1, 1)), D("500"))
        self.assertEqual(cat.amount_for(date(2026, 5, 1)), D("500"))
        self.assertEqual(cat.amount_for(date(2026, 6, 1)), D("650"))
        self.assertEqual(cat.amount_for(date(2027, 3, 1)), D("650"))
        book = services.Book()
        self.assertEqual(book.amount(cat.id, date(2026, 5, 1)), D("500"))
        self.assertEqual(book.amount(cat.id, date(2026, 7, 1)), D("650"))

    def test_transaction_month_defaults_to_its_date(self):
        cat = Category.objects.create(name="Transport")
        t = Transaction.objects.create(category=cat, amount=D("5"), date=date(2026, 6, 10), month=None, title="Bus")
        self.assertEqual(t.month, date(2026, 6, 1))
        late = spend(cat, "88", date(2026, 6, 10), month=date(2026, 5, 20))
        self.assertEqual(late.month, date(2026, 5, 1))
        self.assertTrue(late.counts_elsewhere)


class FundTests(TestCase):
    def setUp(self):
        self.fund = Category.objects.create(name="Travel", kind=Category.Kind.FUND, opening_balance=D("100"))
        self.fund.set_amount(D("200"), date(2026, 1, 1))
        self.fund.set_amount(D("300"), date(2026, 4, 1))

    def test_balance_grows_on_the_first_and_shrinks_by_spends(self):
        spend(self.fund, "450", date(2026, 2, 14), title="Flights")
        spend(self.fund, "-50", date(2026, 3, 2), title="Refund")
        book = services.Book()
        self.assertEqual(book.fund_balance(self.fund, date(2025, 12, 1)), D("100"))
        self.assertEqual(book.fund_balance(self.fund, date(2026, 1, 1)), D("300"))
        self.assertEqual(book.fund_balance(self.fund, date(2026, 2, 1)), D("50"))
        self.assertEqual(book.fund_balance(self.fund, date(2026, 3, 1)), D("300"))
        self.assertEqual(book.fund_balance(self.fund, date(2026, 4, 1)), D("600"))

    def test_spend_counts_toward_its_month_not_its_date(self):
        spend(self.fund, "250", date(2026, 3, 3), month=date(2026, 2, 1))
        book = services.Book()
        self.assertEqual(book.fund_balance(self.fund, date(2026, 2, 1)), D("250"))


class MonthStatusTests(TestCase):
    def test_budgets_and_funds_are_kept_apart(self):
        food = Category.objects.create(name="Food")
        food.set_amount(D("300"), date(2026, 1, 1))
        fun = Category.objects.create(name="Fun")
        fun.set_amount(D("100"), date(2026, 1, 1))
        car = Category.objects.create(name="Car", kind=Category.Kind.FUND)
        car.set_amount(D("150"), date(2026, 1, 1))
        spend(food, "120", date(2026, 3, 5))
        spend(fun, "130", date(2026, 3, 6))
        spend(car, "400", date(2026, 3, 7))
        status = services.month_status(date(2026, 3, 1), today=date(2026, 3, 15))
        self.assertEqual(status.total_budget, D("400"))
        self.assertEqual(status.total_spent, D("250"))
        self.assertEqual(status.left, D("150"))
        self.assertFalse(status.over)
        lines = {b.category.name: b for b in status.budgets}
        self.assertTrue(lines["Fun"].over)
        self.assertEqual(lines["Fun"].percent, 130)
        self.assertEqual(status.funds[0].balance, D("50"))
        self.assertEqual(status.fund_spent, D("400"))
        self.assertEqual(status.days_left, 16)
        self.assertTrue(status.ahead_of_pace)  # 62% spent, 48% of the month gone

    def test_archived_category_without_spends_is_hidden(self):
        old = Category.objects.create(name="Old", archived=True)
        old.set_amount(D("50"), date(2026, 1, 1))
        status = services.month_status(date(2026, 3, 1), today=date(2026, 3, 15))
        self.assertEqual(status.budgets, [])


class AnalysisTests(TestCase):
    def test_counts_complete_months_over_budget(self):
        eat = Category.objects.create(name="Eating out")
        eat.set_amount(D("100"), date(2026, 1, 1))
        rent = Category.objects.create(name="Rent")
        rent.set_amount(D("1000"), date(2026, 1, 1))
        for m, amount in [(1, "120"), (2, "90"), (3, "150"), (4, "130"), (5, "500")]:
            spend(eat, amount, date(2026, m, 10))
            spend(rent, "1000", date(2026, m, 1))
        a = services.analysis(date(2026, 5, 1), 6, today=date(2026, 5, 20))
        # Leading December (no data) is trimmed; May is still running.
        self.assertEqual(a.months[0], date(2026, 1, 1))
        self.assertEqual(a.current, date(2026, 5, 1))
        trend = {t.category.name: t for t in a.categories}
        self.assertEqual(trend["Eating out"].months_over, 3)
        self.assertEqual(trend["Eating out"].months_counted, 4)
        self.assertTrue(trend["Eating out"].consistently_over)
        self.assertEqual(trend["Eating out"].avg_spent, D("122.50"))
        self.assertFalse(trend["Rent"].consistently_over)
        self.assertEqual([t.category.name for t in a.flagged], ["Eating out"])
        self.assertEqual(a.months_over, 3)
        self.assertEqual(a.avg_budget, D("1100.00"))

    def test_months_before_a_category_existed_do_not_count(self):
        new = Category.objects.create(name="Pet")
        new.set_amount(D("80"), date(2026, 3, 1))
        spend(new, "90", date(2026, 3, 4))
        old = Category.objects.create(name="Food")
        old.set_amount(D("100"), date(2026, 1, 1))
        spend(old, "50", date(2026, 1, 4))
        a = services.analysis(date(2026, 3, 1), 3, today=date(2026, 4, 2))
        pet = next(t for t in a.categories if t.category.name == "Pet")
        self.assertEqual(pet.months_counted, 1)
        self.assertEqual(pet.avg_budget, D("80.00"))


class RecurringTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Bills")

    def rule(self, **kw):
        kw.setdefault("title", "Rent")
        kw.setdefault("amount", D("1500"))
        kw.setdefault("category", self.cat)
        kw.setdefault("start_date", date(2026, 1, 31))
        return Recurring.objects.create(**kw)

    def test_month_end_dates_do_not_drift(self):
        r = self.rule()
        self.assertEqual(
            r.dates_between(None, date(2026, 4, 30)),
            [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)],
        )

    def test_generates_only_what_is_due_and_only_once(self):
        r = self.rule(start_date=date(2026, 1, 5))
        self.assertEqual(services.generate_due(date(2026, 3, 4)), 2)
        self.assertEqual(services.generate_due(date(2026, 3, 4)), 0)
        self.assertEqual(services.generate_due(date(2026, 3, 5)), 1)
        self.assertEqual(Transaction.objects.filter(recurring=r).count(), 3)
        r.refresh_from_db()
        self.assertEqual(r.next_date(), date(2026, 4, 5))

    def test_editing_the_rule_changes_entries_still_to_come(self):
        r = self.rule(start_date=date(2026, 1, 5))
        services.generate_due(date(2026, 2, 10))
        r.amount = D("1600")
        r.title = "Rent (new lease)"
        r.save()
        services.generate_due(date(2026, 3, 10))
        rows = list(Transaction.objects.filter(recurring=r).order_by("date").values_list("title", "amount"))
        self.assertEqual(
            rows, [("Rent", D("1500")), ("Rent", D("1500")), ("Rent (new lease)", D("1600"))]
        )

    def test_deleted_entry_is_not_recreated(self):
        r = self.rule(start_date=date(2026, 1, 5))
        services.generate_due(date(2026, 1, 5))
        Transaction.objects.filter(recurring=r).delete()
        self.assertEqual(services.generate_due(date(2026, 1, 20)), 0)

    def test_counts_toward_previous_month(self):
        self.rule(title="Transit bill", start_date=date(2026, 6, 10), month_offset=-1)
        services.generate_due(date(2026, 6, 10))
        t = Transaction.objects.get()
        self.assertEqual((t.date, t.month), (date(2026, 6, 10), date(2026, 5, 1)))

    def test_paused_and_ended_rules_create_nothing(self):
        self.rule(paused=True, start_date=date(2026, 1, 5))
        self.rule(title="Gym", start_date=date(2026, 1, 5), end_date=date(2026, 2, 1))
        services.generate_due(date(2026, 5, 1))
        self.assertEqual(list(Transaction.objects.values_list("title", flat=True)), ["Gym"])

    def test_weekly_and_yearly(self):
        w = self.rule(title="Cleaner", unit="week", every=2, start_date=date(2026, 1, 1))
        y = self.rule(title="Insurance", unit="year", start_date=date(2025, 3, 1))
        self.assertEqual(w.dates_between(None, date(2026, 1, 31)), [date(2026, 1, 1), date(2026, 1, 15), date(2026, 1, 29)])
        self.assertEqual(y.dates_between(None, date(2026, 12, 31)), [date(2025, 3, 1), date(2026, 3, 1)])

    def test_upcoming_lists_future_dates(self):
        self.rule(start_date=date(2026, 1, 5))
        services.generate_due(date(2026, 3, 1))
        self.assertEqual([d for d, _r in services.upcoming(date(2026, 4, 30), today=date(2026, 3, 1))],
                         [date(2026, 3, 5), date(2026, 4, 5)])
