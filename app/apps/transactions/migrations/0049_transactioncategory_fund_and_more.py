import apps.transactions.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_account_kind'),
        ('transactions', '0048_recurringtransaction_keep_at_most'),
    ]

    operations = [
        migrations.AddField(
            model_name='transactioncategory',
            name='account',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='categories',
                to='accounts.account',
                verbose_name='Account',
                help_text="Account this category belongs to. Transactions in this category are forced onto this account.",
            ),
        ),
        migrations.AddField(
            model_name='transactioncategory',
            name='monthly_default_amount',
            field=models.DecimalField(
                blank=True,
                decimal_places=30,
                max_digits=42,
                null=True,
                validators=[
                    apps.transactions.validators.validate_non_negative,
                    apps.transactions.validators.validate_decimal_places,
                ],
                verbose_name='Monthly default amount',
                help_text=(
                    "For sinking-account categories: the monthly auto-allocation "
                    "amount. For normal-account categories: the default monthly budget."
                ),
            ),
        ),
    ]
