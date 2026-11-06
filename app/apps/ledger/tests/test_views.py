from datetime import date, timedelta
from decimal import Decimal as D

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.api.models import APIToken
from apps.ledger.models import Category, Recurring, Transaction
from apps.ledger.months import month_of
from apps.users.models import User


class LedgerViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="alex@example.com", password="pw")
        self.other = User.objects.create_user(email="sam@example.com", password="pw")
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self.month = month_of(self.today)
        self.food = Category.objects.create(name="Food")
        self.food.set_amount(D("400"), self.month)
        self.fund = Category.objects.create(name="Travel", kind=Category.Kind.FUND)
        self.fund.set_amount(D("200"), self.month)
        self.salary = Category.objects.create(name="Salary", kind=Category.Kind.INCOME)

    def test_pages_need_login(self):
        self.client.logout()
        resp = self.client.get(reverse("ledger:home"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])
        self.assertEqual(self.client.get(reverse("ledger:login")).status_code, 200)

    def test_pages_render(self):
        t = Transaction.objects.create(category=self.food, amount=D("12.5"), title="Lunch", date=self.today, month=self.today)
        rule = Recurring.objects.create(title="Rent", amount=D("1000"), category=self.food, start_date=self.today + timedelta(days=3))
        for name, args, query in [
            ("ledger:home", [], ""),
            ("ledger:home", [], "?month=2025-01"),
            ("ledger:history", [], ""),
            ("ledger:history", [], f"?q=lun&month={self.month:%Y-%m}&category={self.food.id}"),
            ("ledger:trends", [], ""),
            ("ledger:trends", [], "?months=6&end=2026-01"),
            ("ledger:category", [self.food.id], ""),
            ("ledger:category", [self.fund.id], ""),
            ("ledger:settings", [], ""),
            ("ledger:budgets_edit", [], ""),
            ("ledger:category_new", [], ""),
            ("ledger:recurring", [], ""),
            ("ledger:recurring_new", [], ""),
            ("ledger:recurring_edit", [rule.id], ""),
            ("ledger:transaction_json", [t.id], ""),
        ]:
            with self.subTest(name=name, query=query):
                resp = self.client.get(reverse(name, args=args) + query)
                self.assertEqual(resp.status_code, 200)
        home = self.client.get(reverse("ledger:home"))
        self.assertContains(home, "$387.50 left")
        self.assertContains(home, 'id="ledger-entry"')
        self.assertContains(home, 'id="entry"')

    def test_add_expense(self):
        resp = self.client.post(reverse("ledger:transaction_create"), {"amount": "12.50", "title": "", "category": self.food.id})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        t = Transaction.objects.get()
        self.assertEqual((t.type, t.amount, t.title, t.date, t.month), ("expense", D("12.50"), "Food", self.today, self.month))
        self.assertEqual(t.created_by, self.user)
        self.assertIn("\u2212$12.50", body["toast"])
        self.assertEqual(body["undo"], reverse("ledger:transaction_delete", args=[t.id]))

    def test_add_money_back_for_an_earlier_month(self):
        self.client.post(
            reverse("ledger:transaction_create"),
            {"type": "income", "amount": "20", "title": "Return", "category": self.food.id, "date": "2026-06-10", "month": "2026-05"},
        )
        t = Transaction.objects.get()
        self.assertEqual((t.type, t.amount, t.date, t.month), ("income", D("20.00"), date(2026, 6, 10), date(2026, 5, 1)))

    def test_add_income(self):
        resp = self.client.post(reverse("ledger:transaction_create"), {"type": "income", "amount": "4200", "title": "Pay", "category": self.salary.id})
        self.assertTrue(resp.json()["ok"])
        self.assertIn("+$4,200.00", resp.json()["toast"])
        home = self.client.get(reverse("ledger:home"))
        self.assertContains(home, "In and out")
        self.assertContains(home, "$4,200.00")
        income_only = self.client.get(reverse("ledger:history") + "?type=income")
        self.assertContains(income_only, "Pay")

    def test_expense_cannot_go_to_an_income_category(self):
        resp = self.client.post(reverse("ledger:transaction_create"), {"type": "expense", "amount": "5", "category": self.salary.id})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("category", resp.json()["errors"])

    def test_add_spend_errors(self):
        resp = self.client.post(reverse("ledger:transaction_create"), {"amount": "0", "title": "x"})
        self.assertEqual(resp.status_code, 400)
        errors = resp.json()["errors"]
        self.assertIn("amount", errors)
        self.assertIn("category", errors)
        self.assertFalse(Transaction.objects.exists())

    def test_repeat_makes_a_rule_that_continues_after_this_entry(self):
        self.client.post(
            reverse("ledger:transaction_create"),
            {"amount": "15", "title": "Music", "category": self.food.id, "date": "2026-01-15", "repeat": "month"},
        )
        rule = Recurring.objects.get()
        t = Transaction.objects.get()
        self.assertEqual(t.recurring, rule)
        self.assertEqual(rule.last_generated, date(2026, 1, 15))
        self.assertEqual(rule.next_date(), date(2026, 2, 15))

    def test_edit_and_delete_spend(self):
        t = Transaction.objects.create(category=self.food, amount=D("10"), title="Lunch", date=self.today, month=self.today, created_by=self.other)
        resp = self.client.post(
            reverse("ledger:transaction_update", args=[t.id]), {"type": "expense", "amount": "11", "title": "Lunch", "category": self.fund.id, "date": self.today.isoformat()}
        )
        self.assertTrue(resp.json()["ok"])
        t.refresh_from_db()
        self.assertEqual((t.amount, t.category, t.created_by), (D("11.00"), self.fund, self.other))
        resp = self.client.post(reverse("ledger:transaction_delete", args=[t.id]))
        self.assertEqual(resp.json()["spend"]["title"], "Lunch")
        self.assertFalse(Transaction.objects.exists())

    def test_everyone_sees_the_shared_ledger(self):
        Transaction.objects.create(category=self.food, amount=D("10"), title="Sam's lunch", date=self.today, month=self.today, created_by=self.other)
        self.assertContains(self.client.get(reverse("ledger:history")), "Sam&#x27;s lunch")

    def test_budget_editor_applies_from_a_month_on(self):
        last = month_of(self.month - timedelta(days=1))
        self.food.set_amount(D("400"), last)
        resp = self.client.post(
            reverse("ledger:budgets_edit"),
            {"from_month": self.month.strftime("%Y-%m"), f"amount_{self.food.id}": "450", f"amount_{self.fund.id}": "200"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.food.amount_for(last), D("400"))
        self.assertEqual(self.food.amount_for(self.month), D("450"))
        self.assertEqual(self.fund.amounts.count(), 1)  # unchanged amount writes nothing

    def test_budget_editor_rejects_bad_amounts(self):
        resp = self.client.post(reverse("ledger:budgets_edit"), {f"amount_{self.food.id}": "lots"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Enter an amount like 250.")
        self.assertEqual(self.food.amount_for(self.month), D("400"))

    def test_create_category(self):
        resp = self.client.post(
            reverse("ledger:category_new"),
            {"name": "Car", "kind": "fund", "amount": "150", "from_month": "2026-01", "opening_balance": "500", "target": ""},
        )
        self.assertEqual(resp.status_code, 302)
        car = Category.objects.get(name="Car")
        self.assertTrue(car.is_fund)
        self.assertEqual(car.amount_for(date(2026, 1, 1)), D("150"))
        self.assertEqual(car.opening_balance, D("500"))
        dup = self.client.post(reverse("ledger:category_new"), {"name": "car", "kind": "budget", "opening_balance": "0"})
        self.assertContains(dup, "already a category")

    def test_delete_category_with_spends_archives_it(self):
        Transaction.objects.create(category=self.food, amount=D("1"), title="x", date=self.today, month=self.today)
        self.client.post(reverse("ledger:category_delete", args=[self.food.id]))
        self.food.refresh_from_db()
        self.assertTrue(self.food.archived)
        self.client.post(reverse("ledger:category_delete", args=[self.fund.id]))
        self.assertFalse(Category.objects.filter(pk=self.fund.pk).exists())

    def test_recurring_form_backfills_from_a_past_first_date(self):
        resp = self.client.post(
            reverse("ledger:recurring_new"),
            {"title": "Phone", "amount": "30", "category": self.food.id, "every": "1", "unit": "month",
             "start_date": (self.today - timedelta(days=40)).isoformat(), "month_offset": "0"},
        )
        self.assertEqual(resp.status_code, 302)
        rule = Recurring.objects.get()
        self.assertEqual(rule.created_by, self.user)
        self.assertGreaterEqual(Transaction.objects.filter(recurring=rule).count(), 2)

    def test_resume_skips_what_fell_due_while_paused(self):
        rule = Recurring.objects.create(
            title="Gym", amount=D("50"), category=self.food, start_date=self.today - timedelta(days=200), paused=True,
            last_generated=self.today - timedelta(days=200),
        )
        self.client.post(reverse("ledger:recurring_toggle", args=[rule.id]))
        rule.refresh_from_db()
        self.assertFalse(rule.paused)
        self.assertLessEqual(Transaction.objects.filter(recurring=rule).count(), 1)

    def test_token_is_shown_once(self):
        self.client.post(reverse("ledger:token_create"), {"name": "Laptop", "scope": "read_write"})
        token = APIToken.objects.get(user=self.user)
        self.assertEqual(token.scope, "read_write")
        self.assertContains(self.client.get(reverse("ledger:settings")), token.key)
        self.assertNotContains(self.client.get(reverse("ledger:settings")), token.key)

    def test_logout_needs_post(self):
        self.assertEqual(self.client.get(reverse("ledger:logout")).status_code, 405)
        self.assertEqual(self.client.post(reverse("ledger:logout")).status_code, 302)
