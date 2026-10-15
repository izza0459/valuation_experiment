"""Adds a stable `value` key to PresetOption.

Conditional-field rules (apps.jobs.field_config) and model logic key off
this rather than the display label, so renaming a label in the admin can
no longer silently break a visibility rule or a calculation.
"""

from django.db import migrations, models
from django.utils.text import slugify


def backfill_values(apps, schema_editor):
    PresetOption = apps.get_model("presets", "PresetOption")
    for option in PresetOption.objects.all():
        option.value = slugify(option.label).replace("-", "_")
        option.save(update_fields=["value"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("presets", "0001_initial")]

    operations = [
        migrations.AlterUniqueTogether(name="presetoption", unique_together=set()),
        migrations.AddField(
            model_name="presetoption",
            name="value",
            field=models.SlugField(
                blank=True,
                default="",
                max_length=100,
                help_text="Stable key stored on the job and referenced by conditional-field "
                "rules (e.g. 'villa'). Renaming the label must not change this.",
            ),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_values, noop),
        migrations.AlterUniqueTogether(
            name="presetoption", unique_together={("field_key", "value")}
        ),
    ]
