from django.db import migrations

from apps.reports.emails import FALLBACK_BODY, FALLBACK_SUBJECT


def apply(apps, schema_editor):
    """The default email a report goes to a bank with; admins edit it."""
    EmailTemplate = apps.get_model("reports", "EmailTemplate")
    if not EmailTemplate.objects.filter(is_default=True).exists():
        EmailTemplate.objects.create(name="Standard report email", subject=FALLBACK_SUBJECT, body=FALLBACK_BODY,
                                     is_default=True)


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0004_email_templates"),
    ]

    operations = [migrations.RunPython(apply, migrations.RunPython.noop)]
