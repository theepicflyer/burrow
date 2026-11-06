"""The ledger MCP toolset, driven through the real ``/mcp`` endpoint.

Each call is a JSON-RPC ``tools/list`` / ``tools/call`` POST to the stateless
streamable-HTTP view, authenticated the way real clients are: a scoped
``APIToken`` (CLI) or an OAuth ``AccessToken`` (claude.ai connector).
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from oauth2_provider.models import get_access_token_model, get_application_model

from apps.api.models import APIToken
from apps.ledger.models import Category, Recurring, Transaction

TODAY = date(2026, 5, 20)

NEW_TOOLS = {
    "get_ledger_info",
    "list_categories",
    "list_transactions",
    "get_month_summary",
    "get_budget_analysis",
    "list_recurring",
    "add_transaction",
    "update_transaction",
    "delete_transaction",
}
WRITE_TOOLS = {"add_transaction", "update_transaction", "delete_transaction"}
# A sample of the old DRF-ViewSet tools (apps/mcp/mcp.py before the ledger).
OLD_TOOLS = {
    "create_transaction",
    "list_accounts",
    "create_account",
    "list_currencies",
    "list_tags",
    "list_entities",
    "list_budgets",
    "update_category",
    "delete_category",
    "list_recurring_transactions",
    "list_exchange_rates",
    "list_dca_strategies",
    "list_import_profiles",
    "list_import_runs",
}


class LedgerMCPTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alex = User.objects.create_user(
            email="alex@example.com", password="x", first_name="Alex", last_name="Rivers"
        )
        cls.sam = User.objects.create_user(email="sam@example.com", password="x")

        cls.groceries = Category.objects.create(name="Groceries", position=1)
        cls.groceries.set_amount(Decimal("400"), date(2026, 1, 1))
        cls.transport = Category.objects.create(name="Transport", position=2)
        cls.transport.set_amount(Decimal("120"), date(2026, 1, 1))
        cls.transport.set_amount(Decimal("150"), date(2026, 5, 1))
        cls.holiday = Category.objects.create(
            name="Holiday", kind=Category.Kind.FUND, opening_balance=Decimal("100"), target=Decimal("2000")
        )
        cls.holiday.set_amount(Decimal("150"), date(2026, 1, 1))
        cls.hobby = Category.objects.create(name="Old hobby", archived=True)
        cls.salary = Category.objects.create(name="Salary", kind=Category.Kind.INCOME)

        def spend(amount, title, category, day, month=None, note="", by=None, type=Transaction.Type.EXPENSE):
            return Transaction.objects.create(
                type=type,
                amount=Decimal(amount),
                title=title,
                category=category,
                date=day,
                month=month or day,
                note=note,
                created_by=by or cls.alex,
            )

        spend("380", "Market run", cls.groceries, date(2026, 1, 15))
        spend("420", "Market run", cls.groceries, date(2026, 2, 10))
        spend("300", "Market run", cls.groceries, date(2026, 3, 8))
        spend("450", "Market run", cls.groceries, date(2026, 4, 12))
        cls.weekly = spend(
            "120.50", "Weekly groceries", cls.groceries, date(2026, 5, 3), note="Fruit and veg", by=cls.sam
        )
        cls.eggs = spend("20", "Returned eggs", cls.groceries, date(2026, 5, 4), type=Transaction.Type.INCOME)
        cls.train = spend("110", "April train pass", cls.transport, date(2026, 5, 10), month=date(2026, 4, 1))
        spend("500", "Flights", cls.holiday, date(2026, 4, 20))
        spend("3000", "Pay", cls.salary, date(2026, 4, 25), type=Transaction.Type.INCOME)
        cls.pay = spend("3200", "Pay", cls.salary, date(2026, 5, 15), type=Transaction.Type.INCOME)

        cls.phone = Recurring.objects.create(
            title="Phone plan",
            amount=Decimal("30"),
            category=cls.transport,
            start_date=date(2026, 3, 15),
            created_by=cls.alex,
        )

        cls.ro_key = APIToken.objects.create(user=cls.alex, name="ro", scope=APIToken.Scope.READ_ONLY).key
        cls.rw_key = APIToken.objects.create(user=cls.alex, name="rw", scope=APIToken.Scope.READ_WRITE).key

        Application = get_application_model()
        app = Application.objects.create(
            name="Test connector",
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="https://claude.ai/api/mcp/auth_callback",
        )
        AccessToken = get_access_token_model()
        expires = timezone.now() + timedelta(days=1)
        for token, scope in [("oauth-read", "mcp:read"), ("oauth-write", "mcp:write"), ("oauth-rw", "mcp:read mcp:write")]:
            AccessToken.objects.create(user=cls.alex, application=app, token=token, expires=expires, scope=scope)

    def setUp(self):
        patcher = mock.patch("django.utils.timezone.localdate", return_value=TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    # ------------------------------------------------------------------ helpers

    RO = property(lambda self: f"Token {self.ro_key}")
    RW = property(lambda self: f"Token {self.rw_key}")
    OAUTH_READ = "Bearer oauth-read"
    OAUTH_WRITE_ONLY = "Bearer oauth-write"
    OAUTH_RW = "Bearer oauth-rw"

    def rpc(self, method, params, auth):
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        resp = self.client.post(
            "/mcp",
            json.dumps(body),
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertNotIn("error", data)
        return data["result"]

    def call_raw(self, auth, name, **arguments):
        """(is_error, payload): the parsed JSON result, or the error text."""
        result = self.rpc("tools/call", {"name": name, "arguments": arguments}, auth)
        text = result["content"][0]["text"]
        if result.get("isError"):
            return True, text
        return False, json.loads(text)

    def call(self, auth, name, **arguments):
        is_error, payload = self.call_raw(auth, name, **arguments)
        self.assertFalse(is_error, payload)
        return payload

    def call_error(self, auth, name, **arguments):
        is_error, payload = self.call_raw(auth, name, **arguments)
        self.assertTrue(is_error, payload)
        return payload


class ToolListTests(LedgerMCPTestCase):
    def test_lists_ledger_tools_and_none_of_the_old_ones(self):
        tools = {t["name"]: t for t in self.rpc("tools/list", {}, self.RO)["tools"]}
        self.assertTrue(NEW_TOOLS <= set(tools), set(tools))
        self.assertFalse(OLD_TOOLS & set(tools))
        for name in NEW_TOOLS:
            self.assertTrue(tools[name]["description"].strip(), name)
            self.assertEqual(tools[name]["annotations"]["readOnlyHint"], name not in WRITE_TOOLS, name)
        add = tools["add_transaction"]["inputSchema"]
        self.assertEqual(set(add["required"]), {"amount", "title", "category_id"})
        self.assertIsNone(add["properties"]["type"]["default"])
        self.assertIn("type", tools["update_transaction"]["inputSchema"]["properties"])
        self.assertIn("type", tools["list_transactions"]["inputSchema"]["properties"])

    def test_unauthenticated_request_is_rejected(self):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        resp = self.client.post(
            "/mcp", json.dumps(body), content_type="application/json", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn("resource_metadata", resp["WWW-Authenticate"])


class ReadToolTests(LedgerMCPTestCase):
    def test_ledger_info(self):
        info = self.call(self.RO, "get_ledger_info")
        self.assertEqual(info["currency"], "$")
        self.assertEqual(info["today"], "2026-05-20")
        self.assertEqual(info["current_month"], "2026-05")
        self.assertEqual(info["signed_in_as"], {"email": "alex@example.com", "name": "Alex Rivers"})
        self.assertFalse(info["can_write"])
        self.assertEqual(set(info["conventions"]["category_kinds"]), {"budget", "fund", "income"})
        self.assertEqual(set(info["conventions"]["type"]), {"expense", "income"})
        self.assertTrue(self.call(self.RW, "get_ledger_info")["can_write"])
        self.assertFalse(self.call(self.OAUTH_READ, "get_ledger_info")["can_write"])
        self.assertTrue(self.call(self.OAUTH_RW, "get_ledger_info")["can_write"])

    def test_today_uses_the_callers_timezone_setting(self):
        # Token requests pass the localization middleware as anonymous, so the
        # toolset must apply the user's timezone itself.
        self.alex.settings.timezone = "Pacific/Auckland"
        self.alex.settings.save()
        with mock.patch("django.utils.timezone.localdate", return_value=TODAY) as localdate:
            self.call(self.RO, "get_ledger_info")
        self.assertEqual(str(localdate.call_args.kwargs["timezone"]), "Pacific/Auckland")

    def test_list_categories(self):
        data = self.call(self.RO, "list_categories")
        by_name = {c["name"]: c for c in data["categories"]}
        self.assertEqual(set(by_name), {"Groceries", "Transport", "Holiday", "Salary"})
        self.assertEqual(by_name["Groceries"]["kind"], "budget")
        self.assertEqual(by_name["Groceries"]["monthly_amount"], "400.00")
        self.assertEqual(by_name["Transport"]["monthly_amount"], "150.00")
        self.assertNotIn("balance", by_name["Groceries"])
        holiday = by_name["Holiday"]
        self.assertEqual(holiday["kind"], "fund")
        self.assertEqual(holiday["monthly_amount"], "150.00")
        # 100 opening + 5 top-ups of 150 - 500 flights.
        self.assertEqual(holiday["balance"], "350.00")
        self.assertEqual(holiday["target"], "2000.00")
        salary = by_name["Salary"]
        self.assertEqual(salary["kind"], "income")
        self.assertIsNone(salary["monthly_amount"])
        self.assertNotIn("balance", salary)

        archived = self.call(self.RO, "list_categories", include_archived=True)["categories"]
        hobby = next(c for c in archived if c["name"] == "Old hobby")
        self.assertTrue(hobby["archived"])

    def test_list_transactions_by_counts_toward_month(self):
        data = self.call(self.RO, "list_transactions", month="2026-04")
        titles = sorted(t["title"] for t in data["transactions"])
        # The train pass is dated in May but counts toward April; the phone plan
        # entry was created by its recurring rule.
        self.assertEqual(titles, ["April train pass", "Flights", "Market run", "Pay", "Phone plan"])
        self.assertEqual(data["total"], 5)
        self.assertEqual((data["total_expenses"], data["total_income"]), ("1090.00", "3000.00"))
        self.assertNotIn("total_amount", data)
        train = next(t for t in data["transactions"] if t["id"] == self.train.id)
        self.assertEqual(train["date"], "2026-05-10")
        self.assertEqual(train["month"], "2026-04")
        self.assertEqual(train["type"], "expense")
        self.assertEqual(train["amount"], "110.00")
        self.assertEqual(train["category"], {"id": self.transport.id, "name": "Transport", "kind": "budget"})
        self.assertIsNone(train["recurring_id"])
        phone = next(t for t in data["transactions"] if t["title"] == "Phone plan")
        self.assertEqual(phone["recurring_id"], self.phone.id)

    def test_list_transactions_filters_and_paging(self):
        data = self.call(self.OAUTH_READ, "list_transactions", search="EGGS")
        self.assertEqual([(t["type"], t["amount"]) for t in data["transactions"]], [("income", "20.00")])

        data = self.call(self.RO, "list_transactions", search="veg")
        self.assertEqual(len(data["transactions"]), 1)
        weekly = data["transactions"][0]
        self.assertEqual(weekly["note"], "Fruit and veg")
        self.assertEqual(weekly["created_by"], {"email": "sam@example.com", "name": ""})

        data = self.call(
            self.RO, "list_transactions", date_from="2026-05-01", date_to="2026-05-31", category_id=self.groceries.id
        )
        self.assertEqual([t["date"] for t in data["transactions"]], ["2026-05-04", "2026-05-03"])
        self.assertEqual((data["total_expenses"], data["total_income"]), ("120.50", "20.00"))

        page = self.call(self.RO, "list_transactions", limit=2, offset=1)
        self.assertEqual(page["total"], 13)  # 10 entered + 3 phone plan entries
        self.assertEqual(len(page["transactions"]), 2)
        self.assertTrue(page["has_more"])
        self.assertEqual(self.call(self.RO, "list_transactions", limit=10_000)["limit"], 500)

    def test_list_transactions_by_type(self):
        data = self.call(self.RO, "list_transactions", type="income")
        self.assertEqual(
            [(t["title"], t["category"]["kind"]) for t in data["transactions"]],
            [("Pay", "income"), ("Returned eggs", "budget"), ("Pay", "income")],
        )
        self.assertEqual((data["total_expenses"], data["total_income"]), ("0.00", "6220.00"))

        data = self.call(self.RO, "list_transactions", type="Expense", month="2026-04")
        self.assertEqual(data["total"], 4)
        self.assertEqual({t["type"] for t in data["transactions"]}, {"expense"})
        self.assertEqual((data["total_expenses"], data["total_income"]), ("1090.00", "0.00"))

    def test_list_transactions_rejects_bad_filters(self):
        self.assertIn('"expense", "income"', self.call_error(self.RO, "list_transactions", type="refund"))
        self.assertIn("2026-05", self.call_error(self.RO, "list_transactions", month="May"))
        self.assertIn("YYYY-MM-DD", self.call_error(self.RO, "list_transactions", date_from="20/05/2026"))
        self.assertIn("no category with id 999", self.call_error(self.RO, "list_transactions", category_id=999))
        self.assertIn(
            "after date_to",
            self.call_error(self.RO, "list_transactions", date_from="2026-05-02", date_to="2026-05-01"),
        )

    def test_recurring_entries_are_generated_once(self):
        self.call(self.RO, "list_transactions")
        self.call(self.RO, "get_month_summary")
        self.assertEqual(Transaction.objects.filter(recurring=self.phone).count(), 3)

    def test_month_summary_current_month(self):
        data = self.call(self.RO, "get_month_summary")
        self.assertEqual(data["month"], "2026-05")
        self.assertTrue(data["is_current_month"])
        self.assertEqual(data["days_left"], 11)
        budgets = {b["name"]: b for b in data["budgets"]}
        self.assertEqual(set(budgets), {"Groceries", "Transport"})  # archived, unused hobby is left out
        self.assertEqual(budgets["Groceries"]["budget"], "400.00")
        self.assertEqual(budgets["Groceries"]["spent"], "100.50")  # net of the returned eggs
        self.assertEqual(budgets["Groceries"]["left"], "299.50")
        self.assertFalse(budgets["Groceries"]["over"])
        self.assertEqual(budgets["Transport"]["spent"], "30.00")
        totals = data["budget_totals"]
        self.assertEqual((totals["budget"], totals["spent"], totals["left"]), ("550.00", "130.50", "419.50"))
        self.assertFalse(totals["ahead_of_pace"])
        self.assertEqual(
            data["funds"],
            [
                {
                    "category_id": self.holiday.id,
                    "name": "Holiday",
                    "topup": "150.00",
                    "spent": "0.00",
                    "balance": "350.00",
                    "target": "2000.00",
                }
            ],
        )
        self.assertEqual(data["incomes"], [{"category_id": self.salary.id, "name": "Salary", "received": "3200.00"}])
        # Out is budgets and funds, net of money back.
        self.assertEqual(data["flow"], {"income": "3200.00", "out": "130.50", "net": "3069.50"})
        self.assertNotIn("currency", data)

    def test_month_summary_past_month(self):
        data = self.call(self.OAUTH_READ, "get_month_summary", month="2026-04")
        self.assertFalse(data["is_current_month"])
        self.assertNotIn("days_left", data)
        budgets = {b["name"]: b for b in data["budgets"]}
        self.assertTrue(budgets["Groceries"]["over"])
        self.assertEqual(budgets["Groceries"]["left"], "-50.00")
        self.assertEqual(budgets["Transport"]["spent"], "140.00")  # train pass + phone plan
        self.assertEqual(data["funds"][0]["spent"], "500.00")
        self.assertEqual(data["funds"][0]["balance"], "200.00")
        self.assertEqual(data["incomes"][0]["received"], "3000.00")
        self.assertEqual(data["flow"], {"income": "3000.00", "out": "1090.00", "net": "1910.00"})

    def test_budget_analysis(self):
        data = self.call(self.RO, "get_budget_analysis", months=5)
        self.assertEqual(data["months"], ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"])
        self.assertEqual(data["current_month"], "2026-05")
        cats = {c["name"]: c for c in data["categories"]}
        self.assertEqual(set(cats), {"Groceries", "Transport"})  # income categories are only in flows
        groceries = cats["Groceries"]
        self.assertEqual((groceries["months_over"], groceries["months_counted"]), (2, 4))
        self.assertTrue(groceries["consistently_over"])
        self.assertEqual(groceries["avg_spent"], "387.50")
        self.assertEqual(groceries["avg_budget"], "400.00")
        self.assertEqual([c["partial"] for c in groceries["by_month"]], [False] * 4 + [True])
        self.assertEqual(groceries["by_month"][-1]["spent"], "100.50")
        self.assertFalse(cats["Transport"]["consistently_over"])
        self.assertEqual(data["flagged"], [{"category_id": self.groceries.id, "name": "Groceries"}])
        self.assertEqual(data["totals"]["months_over"], 1)
        self.assertEqual(data["totals"]["by_month"][3]["spent"], "590.00")

        holiday = data["funds"][0]
        self.assertEqual(
            [b["balance"] for b in holiday["balances"]], ["250.00", "400.00", "550.00", "200.00", "350.00"]
        )
        self.assertEqual(holiday["avg_spent"], "125.00")
        self.assertFalse(holiday["draining"])

        flows = data["flows"]
        self.assertEqual(
            [(f["month"], f["income"], f["out"], f["net"], f["partial"]) for f in flows["by_month"]],
            [
                ("2026-01", "0.00", "380.00", "-380.00", False),
                ("2026-02", "0.00", "420.00", "-420.00", False),
                ("2026-03", "0.00", "330.00", "-330.00", False),
                ("2026-04", "3000.00", "1090.00", "1910.00", False),
                ("2026-05", "3200.00", "130.50", "3069.50", True),
            ],
        )
        # Averages over the four complete months.
        self.assertEqual(flows["months_counted"], 4)
        self.assertEqual((flows["avg_income"], flows["avg_out"], flows["avg_net"]), ("750.00", "555.00", "195.00"))

        self.assertIn("between 1 and 36", self.call_error(self.RO, "get_budget_analysis", months=0))

    def test_list_recurring(self):
        rules = self.call(self.RO, "list_recurring")["recurring"]
        self.assertEqual(len(rules), 1)
        rule = rules[0]
        self.assertEqual(rule["title"], "Phone plan")
        self.assertEqual(rule["type"], "expense")
        self.assertEqual(rule["amount"], "30.00")
        self.assertEqual(rule["category"]["name"], "Transport")
        self.assertEqual((rule["every"], rule["unit"]), (1, "month"))
        self.assertEqual(rule["next_date"], "2026-06-15")
        self.assertEqual(rule["next_counts_toward"], "2026-06")
        self.assertEqual(rule["counts_toward"], "same month")
        self.assertEqual(rule["last_created"], "2026-05-15")
        self.assertFalse(rule["paused"])


class ScopeTests(LedgerMCPTestCase):
    def assert_writes_denied(self, auth, message):
        before = Transaction.objects.count()
        error = self.call_error(
            auth, "add_transaction", amount=5, title="Coffee", category_id=self.groceries.id
        )
        self.assertIn(message, error)
        self.assertIn(message, self.call_error(auth, "update_transaction", id=self.weekly.id, amount=1))
        self.assertIn(message, self.call_error(auth, "delete_transaction", id=self.weekly.id))
        self.assertEqual(Transaction.objects.count(), before)
        self.weekly.refresh_from_db()
        self.assertEqual(self.weekly.amount, Decimal("120.50"))

    def test_read_only_api_token_cannot_write(self):
        self.assert_writes_denied(self.RO, "read-only")

    def test_oauth_token_without_write_scope_cannot_write(self):
        self.assert_writes_denied(self.OAUTH_READ, "mcp:write")

    def test_oauth_token_without_read_scope_cannot_read(self):
        for name in NEW_TOOLS - WRITE_TOOLS:
            self.assertIn("mcp:read", self.call_error(self.OAUTH_WRITE_ONLY, name), name)

    def test_oauth_write_only_token_can_write(self):
        data = self.call(
            self.OAUTH_WRITE_ONLY, "add_transaction", amount="4.20", title="Coffee", category_id=self.groceries.id
        )
        self.assertEqual(data["transaction"]["amount"], "4.20")
        self.assertEqual(data["transaction"]["type"], "expense")


class WriteToolTests(LedgerMCPTestCase):
    def test_add_transaction_defaults(self):
        data = self.call(self.RW, "add_transaction", amount=12.5, title="  Bakery  ", category_id=self.groceries.id)
        tx = Transaction.objects.get(pk=data["transaction"]["id"])
        self.assertEqual((tx.type, tx.amount), (Transaction.Type.EXPENSE, Decimal("12.50")))
        self.assertEqual(tx.title, "Bakery")
        self.assertEqual(tx.date, TODAY)
        self.assertEqual(tx.month, date(2026, 5, 1))
        self.assertEqual(tx.created_by, self.alex)
        self.assertEqual(data["transaction"]["created_by"]["email"], "alex@example.com")
        self.assertEqual(
            data["category_month"],
            {
                "category_id": self.groceries.id,
                "name": "Groceries",
                "kind": "budget",
                "month": "2026-05",
                "budget": "400.00",
                "spent": "113.00",
                "left": "287.00",
                "over": False,
            },
        )

    def test_add_transaction_counting_toward_another_month(self):
        data = self.call(
            self.OAUTH_RW,
            "add_transaction",
            amount="45",
            title="April electricity",
            category_id=self.transport.id,
            date="2026-05-11",
            month="2026-04",
            note="Arrived late",
        )
        tx = Transaction.objects.get(pk=data["transaction"]["id"])
        self.assertEqual((tx.date, tx.month, tx.note), (date(2026, 5, 11), date(2026, 4, 1), "Arrived late"))
        self.assertEqual(tx.created_by, self.alex)
        self.assertEqual(data["category_month"]["month"], "2026-04")
        self.assertEqual(data["category_month"]["spent"], "185.00")
        self.assertTrue(data["category_month"]["over"])

    def test_add_to_fund_reports_balance(self):
        data = self.call(self.RW, "add_transaction", amount=50, title="Hotel deposit", category_id=self.holiday.id)
        self.assertEqual(data["category_month"]["balance"], "300.00")
        self.assertNotIn("budget", data["category_month"])

        # Income in a fund is money put into it.
        data = self.call(
            self.RW, "add_transaction", amount=80, title="Birthday money", category_id=self.holiday.id, type="income"
        )
        self.assertEqual(data["transaction"]["type"], "income")
        self.assertEqual((data["category_month"]["spent"], data["category_month"]["balance"]), ("-30.00", "380.00"))

    def test_add_income(self):
        # type follows the category when left out.
        data = self.call(self.OAUTH_RW, "add_transaction", amount="250", title="Bonus", category_id=self.salary.id)
        tx = Transaction.objects.get(pk=data["transaction"]["id"])
        self.assertEqual((tx.type, tx.amount), (Transaction.Type.INCOME, Decimal("250.00")))
        self.assertEqual(data["transaction"]["amount"], "250.00")
        self.assertEqual(
            data["category_month"],
            {"category_id": self.salary.id, "name": "Salary", "kind": "income", "month": "2026-05", "received": "3450.00"},
        )
        summary = self.call(self.RO, "get_month_summary")
        self.assertEqual(summary["flow"], {"income": "3450.00", "out": "130.50", "net": "3319.50"})

    def test_add_money_back_to_a_budget(self):
        data = self.call(
            self.RW, "add_transaction", amount="10.50", title="Refund", category_id=self.groceries.id, type="income"
        )
        self.assertEqual((data["category_month"]["spent"], data["category_month"]["left"]), ("90.00", "310.00"))
        summary = self.call(self.RO, "get_month_summary")
        self.assertEqual(summary["flow"]["income"], "3200.00")  # money back is not income
        self.assertEqual(summary["flow"]["out"], "120.00")

    def test_add_transaction_validation(self):
        entered = Transaction.objects.filter(recurring=None)  # each call also generates due recurring entries
        before = entered.count()
        cases = [
            ({"category_id": 999}, "no category with id 999"),
            ({"category_id": self.hobby.id}, "archived"),
            ({"amount": "12.345"}, "at most 2 decimal places"),
            ({"amount": "S$12"}, "plain positive number"),
            ({"amount": "$12"}, "plain positive number"),
            ({"amount": "1,200"}, "plain positive number"),
            ({"amount": 0}, "more than 0"),
            ({"amount": "-5"}, 'type "income"'),
            ({"type": "refund"}, '"expense", "income"'),
            ({"type": ""}, '"expense", "income"'),
            ({"category_id": self.salary.id, "type": "expense"}, "Salary is for income. Pick another category"),
            ({"title": "   "}, "title must not be empty"),
            ({"date": "2026-02-30"}, "YYYY-MM-DD"),
            ({"month": "2026-13"}, "YYYY-MM"),
        ]
        for override, message in cases:
            args = {"amount": "10", "title": "Snacks", "category_id": self.groceries.id, **override}
            self.assertIn(message, self.call_error(self.RW, "add_transaction", **args), override)
        self.assertEqual(entered.count(), before)

    def test_update_transaction_partial(self):
        data = self.call(self.RW, "update_transaction", id=self.weekly.id, amount="99.90", note="")
        self.assertEqual(data["changed"], ["amount", "note"])
        self.weekly.refresh_from_db()
        self.assertEqual(self.weekly.amount, Decimal("99.90"))
        self.assertEqual(self.weekly.note, "")
        self.assertEqual(self.weekly.title, "Weekly groceries")
        self.assertEqual(self.weekly.created_by, self.sam)

    def test_update_transaction_type(self):
        data = self.call(self.RW, "update_transaction", id=self.eggs.id, type="expense")
        self.assertEqual(data["changed"], ["type"])
        self.assertEqual(data["transaction"]["type"], "expense")
        self.assertEqual(data["category_month"]["spent"], "140.50")
        self.eggs.refresh_from_db()
        self.assertEqual((self.eggs.type, self.eggs.amount), (Transaction.Type.EXPENSE, Decimal("20.00")))
        self.assertIn(
            '"expense", "income"', self.call_error(self.RW, "update_transaction", id=self.eggs.id, type="refund")
        )
        self.assertIn("more than 0", self.call_error(self.RW, "update_transaction", id=self.eggs.id, amount="-20"))

    def test_update_cannot_leave_an_expense_in_an_income_category(self):
        message = "Salary is for income. Pick another category"
        self.assertIn(message, self.call_error(self.RW, "update_transaction", id=self.pay.id, type="expense"))
        self.assertIn(
            message, self.call_error(self.RW, "update_transaction", id=self.weekly.id, category_id=self.salary.id)
        )
        self.pay.refresh_from_db()
        self.weekly.refresh_from_db()
        self.assertEqual(self.pay.type, Transaction.Type.INCOME)
        self.assertEqual(self.weekly.category, self.groceries)

        data = self.call(
            self.RW, "update_transaction", id=self.weekly.id, category_id=self.salary.id, type="income"
        )
        self.assertEqual(data["changed"], ["category", "type"])
        self.assertEqual(data["category_month"]["received"], "3320.50")

    def test_update_date_moves_month_unless_it_counted_elsewhere(self):
        self.call(self.RW, "update_transaction", id=self.weekly.id, date="2026-04-30")
        self.weekly.refresh_from_db()
        self.assertEqual((self.weekly.date, self.weekly.month), (date(2026, 4, 30), date(2026, 4, 1)))

        self.call(self.RW, "update_transaction", id=self.train.id, date="2026-05-12")
        self.train.refresh_from_db()
        self.assertEqual((self.train.date, self.train.month), (date(2026, 5, 12), date(2026, 4, 1)))

        data = self.call(
            self.OAUTH_RW, "update_transaction", id=self.train.id, month="2026-05", category_id=self.groceries.id
        )
        self.train.refresh_from_db()
        self.assertEqual((self.train.month, self.train.category), (date(2026, 5, 1), self.groceries))
        self.assertEqual(data["category_month"]["name"], "Groceries")

    def test_update_transaction_errors(self):
        self.assertIn("no transaction with id 999", self.call_error(self.RW, "update_transaction", id=999, amount=1))
        self.assertIn("Nothing to change", self.call_error(self.RW, "update_transaction", id=self.weekly.id))
        self.assertIn(
            "archived",
            self.call_error(self.RW, "update_transaction", id=self.weekly.id, category_id=self.hobby.id),
        )

    def test_delete_transaction(self):
        data = self.call(self.OAUTH_RW, "delete_transaction", id=self.weekly.id)
        self.assertEqual(data["deleted"]["title"], "Weekly groceries")
        self.assertEqual(data["category_month"]["spent"], "-20.00")  # only the returned eggs are left
        self.assertFalse(Transaction.objects.filter(pk=self.weekly.id).exists())
        self.assertIn("no transaction", self.call_error(self.RW, "delete_transaction", id=self.weekly.id))
