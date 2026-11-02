from django.db import migrations


def apply(apps, schema_editor):
    """Adds "Test lead" to the lost reasons, just before "Other". Only this
    option: the rest of the list may have been edited in Admin."""
    PresetOption = apps.get_model("presets", "PresetOption")
    if PresetOption.objects.filter(field_key="lost_reason", value="test_lead").exists():
        return
    other = PresetOption.objects.filter(field_key="lost_reason", value="other").first()
    order = other.order if other else PresetOption.objects.filter(field_key="lost_reason").count()
    if other:
        other.order = order + 1
        other.save(update_fields=["order"])
    PresetOption.objects.create(field_key="lost_reason", value="test_lead", label="Test lead", order=order, active=True)


class Migration(migrations.Migration):

    dependencies = [
        ("presets", "0014_option_groups"),
    ]

    operations = [migrations.RunPython(apply, migrations.RunPython.noop)]
