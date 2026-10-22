from django.db import migrations

from apps.presets.dictionary import sync


def apply(apps, schema_editor):
    """Retires the placeholder commentary entries: only wording from the
    "Valuation Report Text Inputs" stays in the library, plus Custom."""
    sync(apps.get_model("presets", "PresetOption"), apps.get_model("presets", "TextLibraryItem"))


class Migration(migrations.Migration):

    dependencies = [
        ("presets", "0010_map_report_text"),
    ]

    operations = [migrations.RunPython(apply, migrations.RunPython.noop)]
