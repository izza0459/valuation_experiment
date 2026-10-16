"""Field dictionary changes (Oct 2026).

* BUA and plot area are entered in sqft: the sqm columns become sqft columns
  and existing values are converted.
* Air conditioning and amenities become multi-selects: a stored value is kept
  as the list's only entry.
* First-floor accommodation, and the title document's own building and
  community names.
* Disclosure has no default; the valuer inserts one of the standard statements.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations, models

SQFT_PER_SQM = Decimal("10.76391")
CENT = Decimal("0.01")


def _convert(apps, factor_fn):
    SummaryData = apps.get_model("jobs", "SummaryData")
    for row in SummaryData.objects.all():
        changed = False
        for name in ("bua_sqft", "plot_area_sqft"):
            value = getattr(row, name)
            if value is not None:
                setattr(row, name, factor_fn(value).quantize(CENT, rounding=ROUND_HALF_UP))
                changed = True
        if changed:
            # .update() skips save() hooks (audit, lock checks): a unit change
            # isn't an edit by anyone.
            SummaryData.objects.filter(pk=row.pk).update(bua_sqft=row.bua_sqft, plot_area_sqft=row.plot_area_sqft)


def sqm_to_sqft(apps, schema_editor):
    _convert(apps, lambda v: v * SQFT_PER_SQM)


def sqft_to_sqm(apps, schema_editor):
    _convert(apps, lambda v: v / SQFT_PER_SQM)


def text_to_list(apps, schema_editor):
    for model_name, old, new in (("InspectionData", "air_conditioning_old", "air_conditioning"),
                                 ("LocationData", "amenities_old", "amenities")):
        Model = apps.get_model("jobs", model_name)
        for pk, value in Model.objects.values_list("pk", old):
            if value and value.strip():
                Model.objects.filter(pk=pk).update(**{new: [value.strip()]})


def list_to_text(apps, schema_editor):
    for model_name, old, new in (("InspectionData", "air_conditioning_old", "air_conditioning"),
                                 ("LocationData", "amenities_old", "amenities")):
        Model = apps.get_model("jobs", model_name)
        for pk, value in Model.objects.values_list("pk", new):
            Model.objects.filter(pk=pk).update(**{old: ", ".join(value or [])})


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0010_more_inspection_options"),
    ]

    operations = [
        # --- areas in sqft ---
        migrations.RenameField("summarydata", "bua_sqm", "bua_sqft"),
        migrations.RenameField("summarydata", "plot_area_sqm", "plot_area_sqft"),
        migrations.AlterField(
            model_name="summarydata",
            name="bua_sqft",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name="summarydata",
            name="plot_area_sqft",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.RunPython(sqm_to_sqft, sqft_to_sqm),
        migrations.AlterField(
            model_name="summarydata",
            name="bua_source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("title_deed", "Title Deed"),
                    ("site_affection_plan", "Site Affection Plan"),
                    ("initial_certificate_of_sale", "Initial Certificate of Sale"),
                    ("spa", "SPA"),
                    ("initial_contract_of_sale", "Initial Contract of Sale"),
                    ("usufruct_certificate", "Usufruct Certificate"),
                    ("floor_plan", "Floor Plan"),
                    ("unit_plan", "Unit Plan"),
                ],
                max_length=40,
            ),
        ),
        migrations.AlterField(
            model_name="summarydata",
            name="disclosure",
            field=models.TextField(blank=True),
        ),
        # --- multi-selects ---
        migrations.RenameField("inspectiondata", "air_conditioning", "air_conditioning_old"),
        migrations.AddField(
            model_name="inspectiondata",
            name="air_conditioning",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RenameField("locationdata", "amenities", "amenities_old"),
        migrations.AddField(
            model_name="locationdata",
            name="amenities",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(text_to_list, list_to_text),
        migrations.RemoveField("inspectiondata", "air_conditioning_old"),
        migrations.RemoveField("locationdata", "amenities_old"),
        # --- new fields ---
        migrations.AddField(
            model_name="inspectiondata",
            name="accommodation_first_floor",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="property",
            name="title_doc_building_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="property",
            name="title_doc_community_name",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
