# Generated by Django 4.1.10 on 2023-09-14 12:49

from django.db import migrations, models
import django.db.models.deletion
import enumfields.fields
import service_onfido.enums
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Company",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("updated", models.DateTimeField(auto_now=True)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("identifier", models.CharField(max_length=100, unique=True)),
                ("secret", models.UUIDField(db_index=True, default=uuid.uuid4)),
                ("active", models.BooleanField(default=True)),
                ("onfido_api_key", models.CharField(max_length=300, null=True)),
                ("onfido_webhook_id", models.CharField(max_length=64, null=True)),
                ("onfido_webhook_token", models.CharField(max_length=300, null=True)),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("updated", models.DateTimeField(auto_now=True)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("identifier", models.UUIDField(default=uuid.uuid4, unique=True)),
                ("token", models.CharField(max_length=200, null=True)),
                ("onfido_id", models.CharField(max_length=64, null=True, unique=True)),
                (
                    "company",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="service_onfido.company",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="DocumentType",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("updated", models.DateTimeField(auto_now=True)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("identifier", models.UUIDField(default=uuid.uuid4, unique=True)),
                ("platform_type", models.CharField(max_length=64)),
                (
                    "onfido_type",
                    enumfields.fields.EnumField(
                        enum=service_onfido.enums.OnfidoDocumentType, max_length=100
                    ),
                ),
                (
                    "side",
                    enumfields.fields.EnumField(
                        blank=True,
                        enum=service_onfido.enums.DocumentTypeSide,
                        max_length=12,
                        null=True,
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="service_onfido.company",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Document",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("updated", models.DateTimeField(auto_now=True)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("identifier", models.UUIDField(default=uuid.uuid4, unique=True)),
                ("platform_id", models.CharField(max_length=64)),
                ("onfido_id", models.CharField(blank=True, max_length=64, null=True)),
                (
                    "type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="service_onfido.documenttype",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_documents",
                        to="service_onfido.user",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="company",
            name="admin",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="admin_company",
                to="service_onfido.user",
            ),
        ),
        migrations.CreateModel(
            name="Check",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("updated", models.DateTimeField(auto_now=True)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("identifier", models.UUIDField(default=uuid.uuid4, unique=True)),
                ("onfido_id", models.CharField(max_length=64)),
                (
                    "status",
                    enumfields.fields.EnumField(
                        default="pending",
                        enum=service_onfido.enums.CheckStatus,
                        max_length=50,
                    ),
                ),
                ("documents", models.ManyToManyField(to="service_onfido.document")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="service_onfido.user",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="PlatformWebhook",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("updated", models.DateTimeField(auto_now=True)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("identifier", models.CharField(max_length=64, unique=True)),
                (
                    "event",
                    enumfields.fields.EnumField(
                        blank=True,
                        enum=service_onfido.enums.WebhookEvent,
                        max_length=100,
                        null=True,
                    ),
                ),
                ("data", models.JSONField(blank=True, null=True)),
                ("completed", models.DateTimeField(null=True)),
                ("failed", models.DateTimeField(null=True)),
                ("tries", models.IntegerField(default=0)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="service_onfido.company",
                    ),
                ),
            ],
            options={
                "unique_together": {("identifier", "company")},
            },
        ),
        migrations.CreateModel(
            name="OnfidoWebhook",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("updated", models.DateTimeField(auto_now=True)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("identifier", models.CharField(max_length=64, unique=True)),
                ("payload", models.JSONField(blank=True, null=True)),
                ("completed", models.DateTimeField(null=True)),
                ("failed", models.DateTimeField(null=True)),
                ("tries", models.IntegerField(default=0)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="service_onfido.company",
                    ),
                ),
            ],
            options={
                "unique_together": {("identifier", "company")},
            },
        ),
        migrations.AddConstraint(
            model_name="documenttype",
            constraint=models.UniqueConstraint(
                condition=models.Q(("side__isnull", False)),
                fields=("company", "platform_type", "onfido_type", "side"),
                name="unique_company_platform_type_onfido_type_side",
            ),
        ),
        migrations.AddConstraint(
            model_name="documenttype",
            constraint=models.UniqueConstraint(
                condition=models.Q(("side__isnull", True)),
                fields=("company", "platform_type", "onfido_type"),
                name="unique_company_platform_type_onfido_type",
            ),
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.UniqueConstraint(
                fields=("user", "platform_id"), name="document_unique_user_platform_id"
            ),
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.UniqueConstraint(
                fields=("user", "onfido_id"), name="document_unique_user_onfido_id"
            ),
        ),
    ]
