"""Leads saved with latitude and longitude the wrong way round (a UAE
longitude in the latitude field and the other way about) are swapped back,
so they show in the UAE on the dashboard map and in the report."""

from decimal import Decimal

from django.db import migrations

LAT = (Decimal("22.5"), Decimal("26.5"))
LNG = (Decimal("51"), Decimal("56.5"))


def swap_back(apps, schema_editor):
    Property = apps.get_model("jobs", "Property")
    for prop in Property.objects.filter(latitude__isnull=False, longitude__isnull=False):
        lat, lng = prop.latitude, prop.longitude
        if LNG[0] <= lat <= LNG[1] and LAT[0] <= lng <= LAT[1]:
            Property.objects.filter(pk=prop.pk).update(latitude=lng, longitude=lat)


class Migration(migrations.Migration):
    dependencies = [("jobs", "0022_lead_lost")]
    operations = [migrations.RunPython(swap_back, migrations.RunPython.noop)]
