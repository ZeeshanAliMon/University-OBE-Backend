"""
Migrate all data from seed-created fake departments to real ones.

Run:
    python manage.py shell < migrate_departments.py
"""
from core.models import (
    Department, Program, GraduateAttribute, Course,
    InstructorProfile, DeptAdminProfile, AdmissionProfile,
    QAProfile, InstructorCourse, AdmissionStudent, CourseAssignment,
)

# Map fake dept_id → real dept_id
MIGRATIONS = [
    ('computing', 'C&T'),   # fake → real computing dept
    ('business',  'DBA'),   # fake → real business dept (if it exists)
]

for fake_id, real_id in MIGRATIONS:
    try:
        fake_dept = Department.objects.get(dept_id=fake_id)
    except Department.DoesNotExist:
        print(f"  – {fake_id} not found, skipping")
        continue

    try:
        real_dept = Department.objects.get(dept_id=real_id)
    except Department.DoesNotExist:
        print(f"  ✗ Real dept {real_id} not found, skipping")
        continue

    print(f"\nMigrating: '{fake_id}' ({fake_dept.name}) → '{real_id}' ({real_dept.name})")

    # GraduateAttributes
    n = GraduateAttribute.objects.filter(department=fake_dept).update(department=real_dept)
    print(f"  ✓ GraduateAttributes: {n}")

    # Courses
    n = Course.objects.filter(department=fake_dept).update(department=real_dept)
    print(f"  ✓ Courses: {n}")

    # InstructorCourses
    n = InstructorCourse.objects.filter(department=fake_dept).update(department=real_dept)
    print(f"  ✓ InstructorCourses: {n}")

    # InstructorProfiles
    n = InstructorProfile.objects.filter(department=fake_dept).update(department=real_dept)
    print(f"  ✓ InstructorProfiles: {n}")

    # DeptAdminProfiles
    n = DeptAdminProfile.objects.filter(department=fake_dept).update(department=real_dept)
    print(f"  ✓ DeptAdminProfiles: {n}")

    # AdmissionProfiles
    n = AdmissionProfile.objects.filter(department=fake_dept).update(department=real_dept)
    print(f"  ✓ AdmissionProfiles: {n}")

    # QAProfiles
    n = QAProfile.objects.filter(department=fake_dept).update(department=real_dept)
    print(f"  ✓ QAProfiles: {n}")

    # AdmissionStudents
    n = AdmissionStudent.objects.filter(department=fake_dept).update(department=real_dept)
    print(f"  ✓ AdmissionStudents: {n}")

    # CourseAssignments (no department field, linked via course/instructor)
    # Nothing to do here

    # Now delete the fake dept
    fake_dept.delete()
    print(f"  ✓ Deleted fake department: {fake_id}")

print("\n── Verification ──")
for d in Department.objects.all():
    progs = Program.objects.filter(department=d)
    gas   = GraduateAttribute.objects.filter(department=d).count()
    ics   = InstructorCourse.objects.filter(department=d).count()
    print(f"  {d.dept_id}: programs={[p.code for p in progs]} GAs={gas} ICs={ics}")
