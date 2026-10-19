"""Brings the dropdowns and the text library in line with the business field
dictionary ("Valuation Report Field Dictionary (3).xlsx", Oct 2026).

For each list: the dictionary's options are created or re-labelled and put in
its order, and options it no longer lists are deactivated (never deleted: a
value already stored on a job must still read properly on its report).
Existing stored keys are kept where an option was only renamed.
"""

from django.db import migrations

from apps.presets.dictionary import sync


def apply(apps, schema_editor):
    sync(apps.get_model("presets", "PresetOption"), apps.get_model("presets", "TextLibraryItem"))


class Migration(migrations.Migration):
    dependencies = [("presets", "0003_textlibraryitem_property_categories_and_more")]

    operations = [migrations.RunPython(apply, migrations.RunPython.noop)]
