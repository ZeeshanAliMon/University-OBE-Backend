"""
Trim course enrollments back to each student's SEMESTER PLAN.

WHY
    seed_full_demo.py enrolled the first 20 students of each program into EVERY
    course of that program (all 8 semesters), not just the courses of their own
    semester. Those rosters live in the database, so on the Dept Admin
    "Student Enrollments" screen those students show every course as
    "Studying Now" (e.g. a 7th-semester student with 44 studying, 0 completed),
    while other students look correct.

WHAT IT DOES
    For every enrolled student (CourseStudent) who is also a registered
    AdmissionStudent with a Semester Plan for their program + current semester:
    keep the enrollment only if the course code is in that plan, otherwise
    remove it.

    Deleting an enrollment also deletes that student's marks in that course
    (they cascade). Set KEEP_MARKED=1 to leave enrollments that already have
    marks untouched.

WHAT IT NEVER TOUCHES
    * closed / finalized courses (their roster is the permanent transcript)
    * students who are not registered AdmissionStudents (added by instructors)
    * students whose program+semester has no Semester Plan
    * courses, programs, plans, instructors, assignments, marks of kept rows

KNOWN LIMIT
    A course added by hand outside the plan ("Add elective / outside course")
    is indistinguishable from seed data, so it is removed too. Re-add those
    from the Student Enrollments screen afterwards if you had any.

!! THIS CANNOT BE UNDONE !!
    Back up first — it's a single SQLite file:
        cp db.sqlite3 "db.sqlite3.backup-$(date +%F-%H%M)"

USAGE
    Dry run (counts only, writes nothing):
        python manage.py shell -c "exec(open('trim_enrollments_to_semester_plan.py').read())"

    Apply for real:
        APPLY=1 python manage.py shell -c "exec(open('trim_enrollments_to_semester_plan.py').read())"

    Apply but keep enrollments that already have marks:
        APPLY=1 KEEP_MARKED=1 python manage.py shell -c "exec(open('trim_enrollments_to_semester_plan.py').read())"
"""
import os
from collections import defaultdict
from django.db import transaction
from core.models import AdmissionStudent, CourseStudent, SemesterPlan, StudentMark, OBEStudentMark

APPLY = os.environ.get('APPLY') == '1'
KEEP_MARKED = os.environ.get('KEEP_MARKED') == '1'

students = {s.reg_no.strip().upper(): s for s in AdmissionStudent.objects.select_related('program')}
plans = {
    (p.program_id, p.semester): {str(c).strip().upper() for c in (p.course_codes or [])}
    for p in SemesterPlan.objects.all()
}

to_delete = []                       # CourseStudent ids
per_student = defaultdict(lambda: [0, 0])   # reg_no -> [kept, removed]
skipped_closed = skipped_unregistered = skipped_no_plan = kept_marked = 0

qs = CourseStudent.objects.select_related('course')
for cs in qs:
    reg = cs.reg_no.strip().upper()
    adm = students.get(reg)
    if cs.course.status == 'closed':
        skipped_closed += 1
        continue
    if adm is None:
        skipped_unregistered += 1
        continue
    allowed = plans.get((adm.program_id, adm.semester))
    if allowed is None:
        skipped_no_plan += 1
        continue
    if cs.course.code.strip().upper() in allowed:
        per_student[reg][0] += 1
        continue
    if KEEP_MARKED and (
        StudentMark.objects.filter(student=cs).exists()
        or OBEStudentMark.objects.filter(student=cs).exists()
    ):
        kept_marked += 1
        per_student[reg][0] += 1
        continue
    per_student[reg][1] += 1
    to_delete.append(cs.id)

affected = {r: v for r, v in per_student.items() if v[1] > 0}

print("=" * 68)
print("TRIM ENROLLMENTS TO SEMESTER PLAN")
print("MODE:", "APPLY — deleting for real" if APPLY else "DRY RUN — nothing will be written")
print("=" * 68)
print(f"\nEnrollments checked ................ {qs.count():>6}")
print(f"  skipped (closed courses) ......... {skipped_closed:>6}")
print(f"  skipped (not registered student) . {skipped_unregistered:>6}")
print(f"  skipped (no plan for semester) ... {skipped_no_plan:>6}")
if KEEP_MARKED:
    print(f"  kept (already has marks) ......... {kept_marked:>6}")
print(f"\nWILL REMOVE ........................ {len(to_delete):>6}  enrollments")
print(f"  students affected ................ {len(affected):>6}")
for reg, (kept, removed) in sorted(affected.items())[:15]:
    adm = students[reg]
    print(f"    {reg:<20} {adm.semester:>4} sem   keep {kept:>3}   remove {removed:>3}")
if len(affected) > 15:
    print(f"    ... and {len(affected) - 15} more students")

if not APPLY:
    print("\nNothing written.")
    print("Back up first:  cp db.sqlite3 \"db.sqlite3.backup-$(date +%F-%H%M)\"")
    print("Then apply:     APPLY=1 python manage.py shell -c \"exec(open('trim_enrollments_to_semester_plan.py').read())\"")
else:
    with transaction.atomic():
        deleted = CourseStudent.objects.filter(id__in=to_delete).delete()
    print(f"\n--- DELETED: {deleted[0]} rows (enrollments + their marks) ---")
    print(f"Enrollments remaining: {CourseStudent.objects.count()}")
    print("\nDone. Reload the Student Enrollments screen: each student now shows")
    print("only the courses of their own semester plan as 'Studying Now'.")
