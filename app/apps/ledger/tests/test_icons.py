from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse

from apps.ledger import icons
from apps.ledger.models import Category
from apps.users.models import User


class IconTests(TestCase):
    def test_library_and_guesses(self):
        self.assertGreater(len(icons.names()), 150)
        self.assertTrue(all(icon in icons.names() for icon in icons.library()["match"].values()))
        self.assertEqual(icons.guess("Groceries"), "shopping-cart")
        self.assertEqual(icons.guess("Eating out"), "fork-knife")
        self.assertEqual(icons.guess("Kids' school fees"), "baby")
        self.assertEqual(icons.guess("Other income"), "coins")  # not the catch-all
        self.assertEqual(icons.guess("Other"), "dots-three")
        self.assertEqual(icons.guess("Zakat"), "")

    def test_display_icon(self):
        auto = Category(name="Transport")
        picked = Category(name="Transport", icon="bicycle")
        letter = Category(name="Transport", icon=icons.LETTER)
        stale = Category(name="Transport", icon="no-such-icon")
        self.assertEqual(auto.display_icon, "bus")
        self.assertEqual(picked.display_icon, "bicycle")
        self.assertEqual(letter.display_icon, "")
        self.assertEqual(stale.display_icon, "bus")

    def test_tile(self):
        render = lambda cat: Template("{% load ledger %}{% category_tile cat %}").render(Context({"cat": cat}))
        self.assertIn("#i-shopping-cart", render(Category(name="Groceries")))
        self.assertIn(">Z<", render(Category(name="Zakat")))
        self.assertIn("acorn", render(Category(name="Rainy day", kind=Category.Kind.FUND)))
        self.assertIn("tile--in", render(Category(name="Salary", kind=Category.Kind.INCOME)))


class IconFormTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user(email="alex@example.com", password="pw"))

    def test_pick_an_icon(self):
        self.assertContains(self.client.get(reverse("ledger:category_new")), 'data-icon-picker')
        resp = self.client.post(reverse("ledger:category_new"), {"name": "Pets", "kind": "budget", "icon": "paw-print", "amount": "50", "opening_balance": "0"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Category.objects.get(name="Pets").display_icon, "paw-print")

    def test_unknown_icon_is_refused(self):
        resp = self.client.post(reverse("ledger:category_new"), {"name": "Pets", "kind": "budget", "icon": "<script>", "opening_balance": "0"})
        self.assertContains(resp, "Pick an icon from the list.")
        self.assertFalse(Category.objects.exists())
