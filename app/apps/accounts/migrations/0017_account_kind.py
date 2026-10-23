from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0016_account_untracked_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="kind",
            field=models.CharField(
                choices=[("normal", "Normal"), ("sinking", "Sinking fund")],
                default="normal",
                help_text="Sinking accounts receive monthly auto-allocations from a main account.",
                max_length=16,
                verbose_name="Kind",
            ),
        ),
    ]
