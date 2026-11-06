from django.core.management.base import BaseCommand, CommandError

from apps.ledger.importer import LedgerNotEmpty, run_import


class Command(BaseCommand):
    help = (
        "Import the old WYGIWYH transactions, categories, budgets, sinking funds and "
        "recurring rules into the household ledger, then print a report."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete every ledger transaction, recurring rule, monthly amount and category first.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run the whole import, print the report, then roll everything back.",
        )

    def handle(self, *args, replace=False, dry_run=False, **options):
        try:
            report = run_import(replace=replace, dry_run=dry_run)
        except LedgerNotEmpty as e:
            raise CommandError(str(e)) from e
        self.stdout.write(report.render())
