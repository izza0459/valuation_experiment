"""Options can sit under a heading. Property categories are grouped as
Bayut groups property types: Residential and Commercial."""

from django.db import migrations, models

COMMERCIAL = {"fitted_office", "shell_core_office", "fitted_retail", "shell_core_retail", "office", "retail",
              "shop", "warehouse", "commercial_plot"}


def group_categories(apps, schema_editor):
    PresetOption = apps.get_model("presets", "PresetOption")
    for option in PresetOption.objects.filter(field_key="property_category", group=""):
        option.group = "Commercial" if option.value in COMMERCIAL else "Residential"
        option.save(update_fields=["group"])


class Migration(migrations.Migration):
    dependencies = [("presets", "0013_lost_reasons")]
    operations = [
        migrations.AddField("presetoption", "group", models.CharField(blank=True, max_length=60)),
        migrations.RunPython(group_categories, migrations.RunPython.noop),
    ]
