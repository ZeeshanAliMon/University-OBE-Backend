from django.db import migrations


def backfill_catalog_course(apps, schema_editor):
    """
    Match each existing InstructorCourse to its catalog Course by
    (code, department, program) so categories/units resolve for rows
    created before the catalog_course FK existed. Where no matching
    Course row exists, one is created so the offering isn't left
    without a home for its marking structure.
    """
    InstructorCourse = apps.get_model('core', 'InstructorCourse')
    Course = apps.get_model('core', 'Course')

    for ic in InstructorCourse.objects.filter(catalog_course__isnull=True):
        course = Course.objects.filter(
            code=ic.code, department=ic.department, program=ic.program
        ).first()

        if course is None:
            course = Course.objects.create(
                code=ic.code,
                title=ic.title,
                department=ic.department,
                program=ic.program,
                credit_hours=ic.credit_hours,
            )

        ic.catalog_course = course
        ic.save(update_fields=['catalog_course'])


def noop_reverse(apps, schema_editor):
    # Nothing to undo — clearing catalog_course on reverse isn't necessary
    # and could destroy data if this migration is re-applied later.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_instructorcourse_catalog_course'),
    ]

    operations = [
        migrations.RunPython(backfill_catalog_course, noop_reverse),
    ]
