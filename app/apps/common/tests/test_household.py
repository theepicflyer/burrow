from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import Account
from apps.budgets.models import Budget
from apps.common.middleware.thread_local import write_current_user
from apps.currencies.models import Currency
from apps.transactions.forms import _default_account
from apps.transactions.models import (
    QuickTransaction,
    Transaction,
    TransactionCategory,
)

STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    "WHITENOISE_AUTOREFRESH": True,
}
HTMX = {"HTTP_HX_REQUEST": "true"}


class HouseholdTestBase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(email="alice@example.com", password="pw")
        self.bob = User.objects.create_user(email="bob@example.com", password="pw")
        currency = Currency.objects.create(code="USD", name="US Dollar")

        write_current_user(self.alice)
        self.account = Account.objects.create(name="Main", currency=currency)
        self.category = TransactionCategory.objects.create(name="Groceries")
        self.txn = Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            date=date(2026, 1, 5),
            reference_date=date(2026, 1, 1),
            amount=Decimal("10"),
            description="Milk",
            category=self.category,
        )
        Budget.objects.create(
            category=self.category, month=date(2026, 1, 1), amount=Decimal("100")
        )
        QuickTransaction.objects.create(
            name="Coffee",
            account=self.account,
            type=Transaction.Type.EXPENSE,
            amount=Decimal("3"),
        )
        write_current_user(None)

    def tearDown(self):
        write_current_user(None)

    def visible_to_bob(self):
        write_current_user(self.bob)
        return {
            "accounts": Account.objects.count(),
            "categories": TransactionCategory.objects.count(),
            "transactions": Transaction.objects.count(),
            "budgets": Budget.objects.count(),
            "quick": QuickTransaction.objects.count(),
        }


@override_settings(HOUSEHOLD_MODE=False, **STATIC)
class HouseholdModeOffTests(HouseholdTestBase):
    def test_other_users_data_stays_private(self):
        self.assertEqual(set(self.visible_to_bob().values()), {0})

    def test_non_owner_cannot_reach_the_account(self):
        self.client.login(username="bob@example.com", password="pw")
        response = self.client.delete(f"/account/{self.account.id}/delete/", **HTMX)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Account.all_objects.exists())


@override_settings(HOUSEHOLD_MODE=True, **STATIC)
class HouseholdModeOnTests(HouseholdTestBase):
    def test_everything_is_visible_to_every_member(self):
        self.assertEqual(
            self.visible_to_bob(),
            {
                "accounts": 1,
                "categories": 1,
                "transactions": 1,
                "budgets": 1,
                "quick": 1,
            },
        )

    def test_anonymous_users_still_see_nothing_private(self):
        self.assertEqual(Account.objects.count(), 0)

    def test_member_can_delete_another_members_account(self):
        self.client.login(username="bob@example.com", password="pw")
        response = self.client.delete(f"/account/{self.account.id}/delete/", **HTMX)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Account.all_objects.exists())

    def test_share_button_is_hidden(self):
        self.client.login(username="alice@example.com", password="pw")
        response = self.client.get("/accounts/list/", **HTMX)
        self.assertNotContains(response, "/share/")

    def test_default_account_falls_back_to_household_main(self):
        write_current_user(self.bob)
        self.assertEqual(_default_account(), self.account)
