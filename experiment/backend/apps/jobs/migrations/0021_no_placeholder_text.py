import re

from django.db import migrations

# A placeholder copied from the library unchanged: the marker and its title.
UNCHANGED = re.compile(r"^\s*\[PLACEHOLDER – replace with approved wording\] [^\n\[\]]{0,120}\.\s*$")
TABS = ["SummaryData", "InspectionData", "LocationData", "ValuationData"]


def apply(apps, schema_editor):
    """Clears placeholder text a job copied from the library and never edited.
    Edited copies are left alone; issuing still refuses them."""
    for name in TABS:
        model = apps.get_model("jobs", name)
        text = [f.name for f in model._meta.fields if f.get_internal_type() in ("TextField", "CharField")]
        lists = [f.name for f in model._meta.fields if f.get_internal_type() == "JSONField"]
        for row in model.objects.all():
            changed = []
            for field in text:
                value = getattr(row, field)
                if isinstance(value, str) and UNCHANGED.match(value):
                    setattr(row, field, "")
                    changed.append(field)
            for field in lists:
                value = getattr(row, field)
                if isinstance(value, list) and any(
                    isinstance(e, dict) and UNCHANGED.match(str(e.get("body", ""))) for e in value
                ):
                    setattr(row, field, [
                        e for e in value if not (isinstance(e, dict) and UNCHANGED.match(str(e.get("body", ""))))
                    ])
                    changed.append(field)
            if changed:
                row.save(update_fields=changed)


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0020_assumptions_as_entries"),
        ("presets", "0011_no_placeholder_text"),
    ]

    operations = [migrations.RunPython(apply, migrations.RunPython.noop)]
