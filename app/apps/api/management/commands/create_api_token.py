from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.api.models import APIToken

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Mint a scoped API token for a user and print the raw key once. "
        "Use this to create the first token headless during cutover."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "username",
            help="USERNAME_FIELD value of the user (email in this project).",
        )
        parser.add_argument("name", help="A label for the token.")
        parser.add_argument(
            "scope",
            choices=[c.value for c in APIToken.Scope],
            help="read_only or read_write.",
        )

    def handle(self, *args, **options):
        username = options["username"]
        try:
            user = User.objects.get(**{User.USERNAME_FIELD: username})
        except User.DoesNotExist:
            raise CommandError(f"No user with {User.USERNAME_FIELD}={username!r}.")

        token = APIToken.objects.create(
            user=user,
            name=options["name"],
            scope=options["scope"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created API token '{token.name}' ({token.get_scope_display()}) "
                f"for {username}."
            )
        )
        self.stdout.write("Key (shown once, store it now):")
        self.stdout.write(self.style.WARNING(token.key))
