"""
Find (and optionally remove) students that sit in course rosters but are NOT
registered in Admissions.

WHY
    A course roster (CourseStudent) is just a registration number + a name; it is
    not linked to the Admissions student list. Rows such as
    "BSCS-2024-003 / Student BSCS 3" can sit in a roster (added by hand, by an old
    script, or through Django admin) without being a real student anywhere else.
    They show up on the Enter Marks sheet with 0 marks.

WHAT IT DOES
    Lists every roster row whose registration number is not an AdmissionStudent,
    grouped by registration number with the courses it appears in. With APPLY=1
    it deletes those roster rows (and the marks entered against them).

    Closed / finalized courses are never touched.

OPTIONS (environment variables)
    APPLY=1            actually delete (default is a dry run)
    ONLY_PREFIX=BSCS-  only rows whose reg no starts with this (case-insensitive)

!! DELETING CANNOT BE UNDONE !!  Back up first:
        cp db.sqlite3 "db.sqlite3.backup-$(date +%F-%H%M)"

USAGE
    Dry run:
        python manage.py shell -c "exec(open('remove_unregistered_roster_students.py').read())"
    Only the BSCS-… ones, for real:
        APPLY=1 ONLY_PREFIX=BSCS- python manage.py shell -c "exec(open('remove_unregistered_roster_students.py').read())"
"""
import os
from collections import defaultdict
from django.db import transaction
from core.models import AdmissionStudent, CourseStudent

APPLY = os.environ.get('APPLY') == '1'
PREFIX = (os.environ.get('ONLY_PREFIX') or '').strip().lower()

registered = {r.strip().upper() for r in AdmissionStudent.objects.values_list('reg_no', flat=True)}

found = defaultdict(lambda: {'name': '', 'courses': [], 'ids': []})
closed_skipped = 0
for cs in CourseStudent.objects.select_related('course'):
    reg = cs.reg_no.strip().upper()
    if reg in registered:
        continue
    if PREFIX and not reg.lower().startswith(PREFIX):
        continue
    if cs.course.status == 'closed':
        closed_skipped += 1
        continue
    f = found[reg]
    f['name'] = f['name'] or cs.name
    f['courses'].append(f"{cs.course.code} [{cs.course.academic_year or '-'}]")
    f['ids'].append(cs.id)

total_rows = sum(len(v['ids']) for v in found.values())
print("=" * 68)
print("UNREGISTERED STUDENTS IN COURSE ROSTERS")
print("MODE:", "APPLY — deleting for real" if APPLY else "DRY RUN — nothing will be written")
if PREFIX:
    print(f"FILTER: registration number starts with '{PREFIX}'")
print("=" * 68)
print(f"\nDistinct students not in Admissions .. {len(found):>5}")
print(f"Roster rows that would be removed .... {total_rows:>5}")
print(f"Skipped (closed courses) ............. {closed_skipped:>5}\n")
for reg, v in sorted(found.items()):
    shown = ', '.join(v['courses'][:4]) + (f" … +{len(v['courses']) - 4}" if len(v['courses']) > 4 else '')
    print(f"  {reg:<20} {v['name'][:24]:<24} in {len(v['courses']):>2} course(s): {shown}")

if not APPLY:
    print("\nNothing written. If this list is exactly what you want gone:")
    print("  APPLY=1 python manage.py shell -c \"exec(open('remove_unregistered_roster_students.py').read())\"")
else:
    ids = [i for v in found.values() for i in v['ids']]
    with transaction.atomic():
        deleted = CourseStudent.objects.filter(id__in=ids).delete()
    print(f"\n--- DELETED {deleted[0]} rows (roster entries + their marks) ---")
