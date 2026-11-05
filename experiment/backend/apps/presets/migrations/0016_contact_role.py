from django.db import migrations

ROLES = [("owner", "Owner"), ("applicant", "Applicant"), ("agent", "Agent / Broker"), ("tenant", "Tenant"),
         ("other", "Other")]


def apply(apps, schema_editor):
    """Who the contact for access is. Only this list: the rest may have been
    edited in Admin."""
    PresetOption = apps.get_model("presets", "PresetOption")
    for order, (value, label) in enumerate(ROLES):
        PresetOption.objects.get_or_create(field_key="contact_role", value=value,
                                           defaults={"label": label, "order": order, "active": True})


class Migration(migrations.Migration):

    dependencies = [
        ("presets", "0015_lost_reason_test_lead"),
    ]

    operations = [migrations.RunPython(apply, migrations.RunPython.noop)]
