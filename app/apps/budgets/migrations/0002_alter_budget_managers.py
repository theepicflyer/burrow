import django.db.models.manager
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('budgets', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelManagers(
            name='budget',
            managers=[
                ('all_objects', django.db.models.manager.Manager()),
            ],
        ),
    ]
