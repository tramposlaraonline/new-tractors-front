import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("preview", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DemoQueuedWithdrawal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("status", models.CharField(default="pending", max_length=8)),
                ("created_at", models.DateTimeField()),
                ("settled_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                          related_name="demo_queued_withdrawals", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "saque de demonstração na fila",
                "verbose_name_plural": "saques de demonstração na fila",
                "indexes": [models.Index(fields=["status", "created_at", "id"], name="demo_queue_pending")],
            },
        ),
    ]
