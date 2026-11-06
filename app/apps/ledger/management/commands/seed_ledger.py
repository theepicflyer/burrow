"""Fill an empty ledger with fictional data for local development and screenshots."""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.ledger import services
from apps.ledger.models import Category, Recurring, Transaction
from apps.ledger.months import add_months, month_of

# name, monthly budget, titles, amount range, chance of a spend on any day
BUDGETS = [
    ("Groceries", 600, ["Supermarket", "Wet market", "Bakery", "Fruit stall"], (8, 90), 0.42),
    ("Eating out", 350, ["Chicken rice", "Laksa", "Coffee", "Dinner out", "Brunch"], (4, 60), 0.4),
    ("Transport", 260, ["Bus top-up", "Taxi", "Train"], (2, 30), 0.3),
    ("Household", 150, ["Cleaning supplies", "Hardware store", "Plants"], (5, 60), 0.12),
    ("Fun", 200, ["Cinema", "Books", "Concert", "Board game"], (10, 80), 0.12),
]
FUNDS = [
    ("Travel", 300, 3600, ["Flights", "Hotel", "Rail pass"]),
    ("Car", 150, None, ["Servicing", "Tyres", "Insurance"]),
    ("Gifts", 80, None, ["Birthday gift", "Wedding gift"]),
]


class Command(BaseCommand):
    help = "Create fictional categories, spends and recurring rules (refuses if the ledger has data)."

    def add_arguments(self, parser):
        parser.add_argument("--months", type=int, default=8)
        parser.add_argument("--seed", type=int, default=7)

    @transaction.atomic
    def handle(self, *args, months, seed, **opts):
        if Category.objects.exists() or Transaction.objects.exists():
            raise CommandError("The ledger already has data.")
        rnd = random.Random(seed)
        today = timezone.localdate()
        first = add_months(month_of(today), -(months - 1))

        for i, (name, budget, titles, (lo, hi), chance) in enumerate(BUDGETS):
            cat = Category.objects.create(name=name, kind=Category.Kind.BUDGET, position=i)
            cat.set_amount(Decimal(budget), first)
            day = first
            while day <= today:
                if rnd.random() < chance:
                    amount = Decimal(rnd.uniform(lo, hi)).quantize(Decimal("0.01"))
                    Transaction.objects.create(amount=amount, title=rnd.choice(titles), category=cat, date=day, month=month_of(day))
                day += timedelta(days=1)
        # Eating out overspends most months; groceries got a bigger budget three months ago.
        Category.objects.get(name="Groceries").set_amount(Decimal("700"), add_months(month_of(today), -2))

        for i, (name, topup, target, titles) in enumerate(FUNDS):
            cat = Category.objects.create(
                name=name, kind=Category.Kind.FUND, position=i, target=target, opening_balance=Decimal("200")
            )
            cat.set_amount(Decimal(topup), first)
            for _ in range(rnd.randint(1, 3)):
                day = first + timedelta(days=rnd.randint(0, (today - first).days))
                Transaction.objects.create(
                    amount=Decimal(rnd.randint(80, 600)), title=rnd.choice(titles), category=cat, date=day, month=month_of(day)
                )

        salary = Category.objects.create(name="Salary", kind=Category.Kind.INCOME)
        interest = Category.objects.create(name="Interest", kind=Category.Kind.INCOME, position=1)
        for who, amount in (("Pay (Alex)", "4200"), ("Pay (Sam)", "3650")):
            Recurring.objects.create(
                type="income", title=who, amount=Decimal(amount), category=salary, unit="month", start_date=first + timedelta(days=24)
            )
        m = first
        while m <= month_of(today):
            Transaction.objects.create(type="income", amount=Decimal(rnd.randint(8, 30)), title="Savings interest",
                                       category=interest, date=m, month=m)
            m = add_months(m, 1)
        Transaction.objects.create(type="income", amount=Decimal("24.90"), title="Returned shoes",
                                   category=Category.objects.get(name="Fun"), date=today - timedelta(days=3), month=month_of(today))

        transport = Category.objects.get(name="Transport")
        start = add_months(first, 1) + timedelta(days=9)
        Recurring.objects.create(
            title="Transit card bill", amount=Decimal("96.40"), category=transport, unit="month",
            start_date=start, month_offset=-1,
        )
        Recurring.objects.create(
            title="Music subscription", amount=Decimal("11.98"), category=Category.objects.get(name="Fun"),
            unit="month", start_date=first + timedelta(days=rnd.randint(0, 27)),
        )
        created = services.generate_due(today)
        self.stdout.write(self.style.SUCCESS(f"Seeded {Transaction.objects.count()} transactions ({created} recurring)."))
