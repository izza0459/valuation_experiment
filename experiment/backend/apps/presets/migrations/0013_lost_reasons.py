from django.db import migrations

from apps.presets.dictionary import sync


def apply(apps, schema_editor):
    """Adds the reasons a lead can be lost for."""
    sync(apps.get_model("presets", "PresetOption"), apps.get_model("presets", "TextLibraryItem"))


class Migration(migrations.Migration):

    dependencies = [
        ("presets", "0012_library_soft_delete"),
    ]

    operations = [migrations.RunPython(apply, migrations.RunPython.noop)]
