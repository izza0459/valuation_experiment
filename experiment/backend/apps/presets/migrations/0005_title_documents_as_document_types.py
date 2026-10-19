"""Every title document type (field dictionary: Title Deed, Initial Contract of
Sale, SPA, Usufruct Certificate, Sale Certificate, Site Plan, Site Affection
Plan) is also a document type, so the title document uploaded on the Check
List can say which one it is. Same keys as the Title Document dropdown.
Other document types are left as they are."""

from django.db import migrations

TITLE_DOCUMENTS = [
    ("Title Deed", "title_deed"),
    ("Initial Contract of Sale", "initial_contract_of_sale"),
    ("Sales and Purchase Agreement (SPA)", "spa"),
    ("Usufruct Certificate", "usufruct_certificate"),
    ("Sale Certificate", "sale_certificate"),
    ("Site Plan", "site_plan"),
    ("Site Affection Plan", "site_affection_plan"),
]


def add(apps, schema_editor):
    PresetOption = apps.get_model("presets", "PresetOption")
    for order, (label, value) in enumerate(TITLE_DOCUMENTS):
        row, created = PresetOption.objects.get_or_create(
            field_key="document_type", value=value, defaults={"label": label, "order": order}
        )
        if not created and not row.active:
            row.active = True
            row.save(update_fields=["active"])


class Migration(migrations.Migration):
    dependencies = [("presets", "0004_sync_with_field_dictionary")]

    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
