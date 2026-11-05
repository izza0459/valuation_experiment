import re

from django.db import migrations

OLD = re.compile(r"^BYT-\d{4}-(\d+)(-v\d+)?$")


def drop_prefix(apps, schema_editor):
    """BYT-2026-00014 -> 00014 (and BYT-2026-00014-v2 -> 00014-v2). Issued
    jobs too: the reference is one record. A number that two years both used
    keeps its old form, so no two jobs share a reference. One counter carries
    on from the highest number."""
    Job = apps.get_model("jobs", "Job")
    ReferenceCounter = apps.get_model("jobs", "ReferenceCounter")
    rows = list(Job.objects.values_list("pk", "bayut_internal_reference_no"))
    new = {pk: OLD.sub(r"\1\2", ref) for pk, ref in rows if OLD.match(ref)}
    taken = [ref for pk, ref in rows if pk not in new]
    counts = {}
    for ref in [*new.values(), *taken]:
        counts[ref] = counts.get(ref, 0) + 1
    highest = 0
    for pk, ref in new.items():
        if counts[ref] > 1:
            continue
        # update(): an issued job's save() refuses any change.
        Job.objects.filter(pk=pk).update(bayut_internal_reference_no=ref)
        highest = max(highest, int(ref.split("-")[0]))
    for counter in ReferenceCounter.objects.exclude(year=0):
        highest = max(highest, counter.last_value)
    shared, _ = ReferenceCounter.objects.get_or_create(year=0)
    shared.last_value = max(shared.last_value, highest)
    shared.save(update_fields=["last_value"])


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0028_contact_role"),
    ]

    operations = [migrations.RunPython(drop_prefix, migrations.RunPython.noop)]
