from django.db import migrations

from apps.presets.dictionary import sync


def apply(apps, schema_editor):
    """Adds the valuation commentary templates (Nov 2026), one per property
    type, to the library."""
    sync(apps.get_model("presets", "PresetOption"), apps.get_model("presets", "TextLibraryItem"))


class Migration(migrations.Migration):

    dependencies = [
        ("presets", "0016_contact_role"),
    ]

    operations = [migrations.RunPython(apply, migrations.RunPython.noop)]
