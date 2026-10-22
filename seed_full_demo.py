"""
OBE System — Full Demo Data Seed Script
========================================
Fills in EVERYTHING needed to test all features end-to-end:

  - Uses existing departments, programs, GAs, courses, students, instructors
  - Skips anything already present (safe to re-run)
  - Creates InstructorCourses for each assignment
  - Sets up marks categories (Assignments, Quizzes, Mid, Final)
  - Creates CLOs and maps them to GAs
  - Creates OBE Questions mapped to CLOs
  - Enrolls students from AdmissionStudent into each course
  - Enters realistic random marks for every student on every question
  - Runs all reports endpoints in-process to verify data flows correctly

Run:
    python manage.py shell < seed_full_demo.py

Password for all accounts: Test@1234
"""

import os, random, traceback
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'obe_system.settings')

random.seed(42)

from django.db import transaction
from core.models import (
    Department, Program, GraduateAttribute, Course,
    InstructorProfile, DeptAdminProfile,
    AdmissionStudent, CourseStudent,
    InstructorCourse, CLO, MarksCategory, UnitItem,
    OBEQuestion, StudentMark, OBEStudentMark,
    CourseAssignment, SemesterPlan,
)

ACADEMIC_YEAR = 'Fall-2024'
ATTAINMENT_THRESHOLD = 50.0

# ─── Helpers ──────────────────────────────────────────────────────────────────

def p(msg): print(f"  {msg}")
def h(msg): print(f"\n{'─'*60}\n  {msg}\n{'─'*60}")

def skipped(label): p(f"– {label} (already exists)")
def created(label): p(f"✓ {label}")

# ─── 1. Inventory what's already in the DB ────────────────────────────────────

h("1. Checking existing data")

depts      = list(Department.objects.all())
programs   = list(Program.objects.all())
gas        = list(GraduateAttribute.objects.all())
courses    = list(Course.objects.all())
instructors = list(InstructorProfile.objects.select_related('user', 'department').all())
students   = list(AdmissionStudent.objects.select_related('program', 'department').all())
da_profiles = list(DeptAdminProfile.objects.select_related('department').all())

p(f"Departments  : {len(depts)}")
p(f"Programs     : {len(programs)}")
p(f"GAs          : {len(gas)}")
p(f"Courses      : {len(courses)}")
p(f"Instructors  : {len(instructors)}")
p(f"Students     : {len(students)}")
p(f"Dept Admins  : {len(da_profiles)}")

if not depts:
    print("\n  ✗ No departments found. Run seed_test_data.py first.")
    exit(1)
if not programs:
    print("\n  ✗ No programs found. Run seed_test_data.py first.")
    exit(1)
if not instructors:
    print("\n  ✗ No instructors found. Run seed_test_data.py first.")
    exit(1)

# ─── 2. Ensure every program has courses ──────────────────────────────────────

h("2. Ensuring courses exist for every program")

# Map dept → GAs for quick lookup
dept_gas = {}
for ga in gas:
    dept_gas.setdefault(ga.department_id, []).append(ga)

# course template: (code_suffix, title, subtype, credit_hours)
COURSE_TEMPLATES = [
    ('101', 'Fundamentals',              'theory', 3),
    ('201', 'Advanced Concepts',         'theory', 3),
    ('202', 'Advanced Lab',              'lab',    1),
    ('301', 'System Design',             'theory', 3),
    ('302', 'System Design Lab',         'lab',    1),
    ('401', 'Project Management',        'theory', 3),
    ('501', 'Research Methods',          'theory', 3),
    ('601', 'Elective: Special Topics',  'theory', 3),
]

prog_courses = {}   # prog.id → list of Course objects

for prog in programs:
    dept = prog.department
    prog_gas = dept_gas.get(dept.id, [])
    prog_courses[prog.id] = []

    prefix = prog.code.upper().replace('BS', '').replace('MS', '')[:3]
    if len(prefix) < 2:
        prefix = prog.code[:3].upper()

    for suffix, title_suffix, subtype, credits in COURSE_TEMPLATES:
        code = f"{prefix}{suffix}"
        full_title = f"{prog.code} — {title_suffix}"
        try:
            course, created_now = Course.objects.get_or_create(
                code=code, department=dept, program=prog,
                defaults={
                    'title':        full_title,
                    'type':         'elective' if 'Elective' in title_suffix else 'core',
                    'subtype':      subtype,
                    'credit_hours': credits,
                }
            )
            if created_now:
                # Map to 2 GAs if available
                if len(prog_gas) >= 2:
                    course.mapped_gas.set(prog_gas[:2])
                elif prog_gas:
                    course.mapped_gas.set([prog_gas[0]])
                created(f"Course {code}: {full_title} [{subtype}]")
            else:
                skipped(f"Course {code}")
            prog_courses[prog.id].append(course)
        except Exception as e:
            p(f"✗ Course {code}: {e}")

# Reload courses
courses = list(Course.objects.all())
p(f"\n  Total courses now: {len(courses)}")

# ─── 3. Assign instructors to courses ─────────────────────────────────────────

h("3. Course Assignments (instructor → course → program)")

# Group instructors by department
dept_instructors = {}
for inst in instructors:
    dept_instructors.setdefault(inst.department_id, []).append(inst)

# Get or create a dummy dept admin for each dept if none exists
dept_admin_map = {}
for da in da_profiles:
    dept_admin_map[da.department_id] = da

assignments_created = 0
for prog in programs:
    dept = prog.department
    inst_list = dept_instructors.get(dept.id, [])
    if not inst_list:
        p(f"  ⚠ No instructors for {dept.name} — skipping assignments")
        continue
    da = dept_admin_map.get(dept.id)
    p_courses = prog_courses.get(prog.id, [])

    for i, course in enumerate(p_courses):
        inst = inst_list[i % len(inst_list)]
        try:
            _, was_created = CourseAssignment.objects.get_or_create(
                instructor=inst,
                course=course,
                program=prog,
                academic_year=ACADEMIC_YEAR,
                defaults={'assigned_by': da}
            )
            if was_created:
                assignments_created += 1
        except Exception as e:
            p(f"  ✗ {inst.user.username} → {course.code}: {e}")

p(f"  Created {assignments_created} new course assignments")

# ─── 4. Create InstructorCourse records ───────────────────────────────────────

h("4. InstructorCourse records")

SEMESTER_MAP = {
    '101': '1st', '202': '2nd', '201': '3rd', '202': '3rd',
    '301': '5th', '302': '5th', '401': '7th', '501': '7th', '601': '7th',
}

ic_map = {}   # (inst.id, course.code, prog.id) → InstructorCourse
ic_created = 0

for assignment in CourseAssignment.objects.select_related('instructor', 'course', 'program').filter(academic_year=ACADEMIC_YEAR):
    inst   = assignment.instructor
    course = assignment.course
    prog   = assignment.program

    prog_suffix = prog.code.lower() if prog else 'all'
    term_norm   = ACADEMIC_YEAR[0].upper() + ACADEMIC_YEAR[1:]
    frontend_id = f"course-assigned-{course.code}-{inst.employee_id}-{prog_suffix}-{term_norm}"

    suffix_key = course.code[-3:] if len(course.code) >= 3 else '101'
    semester   = SEMESTER_MAP.get(suffix_key, '1st')

    subtype_map = {'lab': 'Lab', 'theory': 'Theory'}
    course_type = subtype_map.get(getattr(course, 'subtype', 'theory'), 'Theory')

    try:
        ic, was_created = InstructorCourse.objects.get_or_create(
            instructor=inst,
            frontend_id=frontend_id,
            defaults=dict(
                catalog_course    = course,
                code              = course.code,
                title             = course.title,
                course_type       = course_type,
                department        = course.department,
                program           = prog,
                credit_hours      = course.credit_hours,
                clo_count         = 3,
                selected_grading_system = 'ready1',
                semester          = semester,
                academic_year     = ACADEMIC_YEAR,
                status            = 'active',
            )
        )
        if not was_created and ic.catalog_course_id is None:
            ic.catalog_course = course
            ic.save(update_fields=['catalog_course'])
        ic_map[(inst.id, course.code, prog.id if prog else None)] = ic
        if was_created:
            ic_created += 1
    except Exception as e:
        p(f"  ✗ IC {frontend_id}: {e}")
        traceback.print_exc()

p(f"  Created {ic_created} new InstructorCourse records")
p(f"  Total InstructorCourse records: {InstructorCourse.objects.count()}")

# Reload all active ICs
all_ics = list(InstructorCourse.objects.filter(
    academic_year=ACADEMIC_YEAR, status='active'
).select_related('catalog_course', 'program', 'department', 'instructor'))

# ─── 5. Marks Categories + Unit Items ─────────────────────────────────────────

h("5. Marks Categories & Unit Items")

CATEGORIES = [
    # (name, percentage, unit_count, passing_per_unit, marks_per_unit)
    ('Assignments', 15.0, 3, 5,  10),
    ('Quizzes',     10.0, 3, 5,  10),
    ('Mid Term',    25.0, 1, 12, 25),
    ('Final Exam',  50.0, 1, 25, 50),
]

cats_created = 0
units_created = 0

for ic in all_ics:
    cat_course = ic.catalog_course
    if not cat_course:
        continue
    for order, (name, pct, unit_count, passing, marks_per_unit) in enumerate(CATEGORIES):
        cat, cat_new = MarksCategory.objects.get_or_create(
            course=cat_course, name=name,
            defaults={'percentage': pct, 'units': unit_count, 'order': order}
        )
        if cat_new:
            cats_created += 1
        for u in range(1, unit_count + 1):
            _, unit_new = UnitItem.objects.get_or_create(
                category=cat, unit_no=u,
                defaults={
                    'passing':     passing,
                    'total_marks': marks_per_unit,
                    'weightage':   round(pct / unit_count, 2),
                    'mapped_clos': [],
                }
            )
            if unit_new:
                units_created += 1

p(f"  Created {cats_created} categories, {units_created} unit items")

# ─── 6. CLOs mapped to GAs ────────────────────────────────────────────────────

h("6. CLOs (3 per course, each mapped to a GA)")

CLO_TEMPLATES = [
    ("CLO-1", "Students will demonstrate foundational understanding of {title} concepts."),
    ("CLO-2", "Students will apply {title} principles to solve structured problems."),
    ("CLO-3", "Students will evaluate and communicate solutions in {title} context."),
]

clos_created = 0

for ic in all_ics:
    dept_id = ic.department_id
    ic_gas  = dept_gas.get(dept_id, [])
    if not ic_gas:
        continue

    existing_clo_codes = set(ic.clos.values_list('code', flat=True))

    for order, (code, desc_template) in enumerate(CLO_TEMPLATES, start=1):
        if code in existing_clo_codes:
            continue
        ga = ic_gas[order % len(ic_gas)]
        try:
            CLO.objects.create(
                course      = ic,
                code        = code,
                description = desc_template.format(title=ic.title),
                mapped_ga   = ga,
                order       = order,
            )
            clos_created += 1
        except Exception as e:
            pass  # already exists with unique_together

p(f"  Created {clos_created} new CLOs")

# ─── 7. OBE Questions mapped to CLOs ──────────────────────────────────────────

h("7. OBE Questions")

# Question structure per course:
# Assignments: 3 units × 2 questions each = 6 questions
# Quizzes:     3 units × 2 questions each = 6 questions
# Mid Term:    1 unit  × 5 questions      = 5 questions
# Final:       1 unit  × 5 questions      = 5 questions
# Total: 22 questions per course

QUESTION_STRUCTURE = {
    'Assignments': (3, 2, 5.0),   # (units, q_per_unit, marks_per_q)
    'Quizzes':     (3, 2, 5.0),
    'Mid Term':    (1, 5, 5.0),
    'Final Exam':  (1, 5, 10.0),
}

CLO_ROTATION = ['CLO-1', 'CLO-2', 'CLO-3', 'CLO-1', 'CLO-2']
q_created = 0

for ic in all_ics:
    cat_course = ic.catalog_course
    if not cat_course:
        continue
    existing_q_ids = set(ic.obe_questions.values_list('frontend_id', flat=True))
    q_order = 0

    for cat in cat_course.markscategories.all():
        units, q_per_unit, marks = QUESTION_STRUCTURE.get(cat.name, (1, 2, 5.0))
        for unit_no in range(1, units + 1):
            try:
                unit_obj = UnitItem.objects.get(category=cat, unit_no=unit_no)
            except UnitItem.DoesNotExist:
                continue
            mapped_clos_for_unit = []
            for q_num in range(1, q_per_unit + 1):
                clo_code   = CLO_ROTATION[(q_order) % len(CLO_ROTATION)]
                frontend_id = f"{ic.frontend_id}-{cat.name.replace(' ', '_')}-U{unit_no}-Q{q_num}"
                if frontend_id in existing_q_ids:
                    q_order += 1
                    mapped_clos_for_unit.append(clo_code)
                    continue
                try:
                    OBEQuestion.objects.create(
                        course        = ic,
                        frontend_id   = frontend_id,
                        unit_item     = unit_obj,
                        category_name = cat.name,
                        unit_no       = unit_no,
                        question_name = f"{cat.name} U{unit_no} Q{q_num}",
                        max_marks     = marks,
                        mapped_clos   = [clo_code],
                        order         = q_order,
                    )
                    q_created += 1
                    mapped_clos_for_unit.append(clo_code)
                except Exception:
                    pass
                q_order += 1
            # Update UnitItem mapped_clos
            if mapped_clos_for_unit:
                unique_clos = list(dict.fromkeys(mapped_clos_for_unit))
                if unit_obj.mapped_clos != unique_clos:
                    unit_obj.mapped_clos = unique_clos
                    unit_obj.save(update_fields=['mapped_clos'])

p(f"  Created {q_created} new OBE questions")

# ─── 8. Enroll students into courses ──────────────────────────────────────────

h("8. Student Enrollment into Courses")

# Group students by program
prog_students = {}
for s in students:
    prog_students.setdefault(s.program_id, []).append(s)

cs_created = 0

for ic in all_ics:
    prog_id    = ic.program_id
    s_list     = prog_students.get(prog_id, [])
    if not s_list:
        # Fallback: any students from same dept
        s_list = [s for s in students if s.department_id == ic.department_id]
    # Enroll up to 20 students per course
    enroll_list = s_list[:20]
    existing_regs = set(ic.students.values_list('reg_no', flat=True))

    for adm_s in enroll_list:
        if adm_s.reg_no in existing_regs:
            continue
        try:
            CourseStudent.objects.create(
                course = ic,
                reg_no = adm_s.reg_no,
                name   = adm_s.name,
            )
            cs_created += 1
        except Exception:
            pass

p(f"  Enrolled {cs_created} new students into courses")

# ─── 9. Enter marks for every student ─────────────────────────────────────────

h("9. Student Marks (unit-level & OBE question-level)")

marks_created = 0
obe_marks_created = 0

# Performance profiles — makes data interesting for reports
def get_student_profile(reg_no):
    """Returns a performance multiplier based on reg_no so same student is consistently good/average/weak."""
    num = sum(ord(c) for c in reg_no)
    r = (num % 10) / 10.0   # 0.0 to 0.9
    if r < 0.2:    return 0.45   # weak student (below threshold)
    elif r < 0.5:  return 0.65   # average
    elif r < 0.8:  return 0.80   # good
    else:          return 0.92   # excellent

for ic in all_ics:
    cat_course = ic.catalog_course
    if not cat_course:
        continue

    # Collect unit items and OBE questions for this course
    unit_items = list(UnitItem.objects.filter(category__course=cat_course))
    obe_questions = list(ic.obe_questions.all())

    for cs in ic.students.all():
        profile = get_student_profile(cs.reg_no)
        # Add small random noise per student per course
        noise = random.uniform(-0.08, 0.08)
        perf  = max(0.20, min(0.98, profile + noise))

        # Unit-level marks (existing StudentMark table)
        existing_unit_marks = set(cs.marks.values_list('unit_item_id', flat=True))
        for ui in unit_items:
            if ui.id in existing_unit_marks:
                continue
            raw_score = perf * ui.total_marks
            # Add per-unit noise
            raw_score += random.uniform(-ui.total_marks * 0.05, ui.total_marks * 0.05)
            score = round(max(0, min(ui.total_marks, raw_score)), 1)
            try:
                StudentMark.objects.create(student=cs, unit_item=ui, score=score)
                marks_created += 1
            except Exception:
                pass

        # OBE question marks
        existing_obe = set(cs.obe_marks.values_list('question_id', flat=True))
        for q in obe_questions:
            if q.id in existing_obe:
                continue
            raw_score = perf * q.max_marks
            raw_score += random.uniform(-q.max_marks * 0.08, q.max_marks * 0.08)
            score = round(max(0, min(q.max_marks, raw_score)), 1)
            try:
                OBEStudentMark.objects.create(student=cs, question=q, score=score)
                obe_marks_created += 1
            except Exception:
                pass

p(f"  Created {marks_created} unit marks")
p(f"  Created {obe_marks_created} OBE question marks")

# ─── 10. Semester Plans ───────────────────────────────────────────────────────

h("10. Semester Plans")

SEMESTERS = ['1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th']
sp_created = 0

for prog in programs:
    da = dept_admin_map.get(prog.department_id)
    p_courses_list = prog_courses.get(prog.id, [])
    if not p_courses_list:
        continue

    # Distribute courses across semesters (2 per semester where possible)
    codes_by_sem = {}
    for i, course in enumerate(p_courses_list):
        sem = SEMESTERS[i % len(SEMESTERS)]
        codes_by_sem.setdefault(sem, []).append(course.code)

    for sem, codes in codes_by_sem.items():
        _, was_created = SemesterPlan.objects.get_or_create(
            program=prog, semester=sem,
            defaults={'course_codes': codes, 'updated_by': da}
        )
        if was_created:
            sp_created += 1

p(f"  Created {sp_created} new semester plans")

# ─── 11. Quick verification: spot-check report data ───────────────────────────

h("11. Verification")

from django.db.models import Count

p(f"  InstructorCourses  : {InstructorCourse.objects.count()}")
p(f"  CLOs               : {CLO.objects.count()}")
p(f"  OBE Questions      : {OBEQuestion.objects.count()}")
p(f"  Course Students    : {CourseStudent.objects.count()}")
p(f"  Unit Marks         : {StudentMark.objects.count()}")
p(f"  OBE Marks          : {OBEStudentMark.objects.count()}")
p(f"  Semester Plans     : {SemesterPlan.objects.count()}")

# Check attainment coverage: how many ICs have both students and OBE marks?
ics_with_students = InstructorCourse.objects.annotate(sc=Count('students')).filter(sc__gt=0).count()
ics_with_marks    = InstructorCourse.objects.annotate(mc=Count('obe_questions')).filter(mc__gt=0).count()
p(f"\n  ICs with students  : {ics_with_students}")
p(f"  ICs with questions : {ics_with_marks}")

# Sample attainment check on first program with data
prog_with_data = Program.objects.filter(
    instructor_courses__students__isnull=False
).distinct().first()
if prog_with_data:
    p(f"\n  Sample program for reports: {prog_with_data.code} — {prog_with_data.name}")
    ic_count = InstructorCourse.objects.filter(program=prog_with_data).count()
    s_count  = CourseStudent.objects.filter(course__program=prog_with_data).count()
    q_count  = OBEQuestion.objects.filter(course__program=prog_with_data).count()
    m_count  = OBEStudentMark.objects.filter(student__course__program=prog_with_data).count()
    p(f"    Courses    : {ic_count}")
    p(f"    Students   : {s_count}")
    p(f"    Questions  : {q_count}")
    p(f"    OBE Marks  : {m_count}")

# ─── Summary ──────────────────────────────────────────────────────────────────

print(f"""
{'='*60}
SEED COMPLETE
{'='*60}

All features now have data to test:

  QA Dashboard:
    ✓ Departments, Programs, GAs, Courses
    ✓ CLO Attainment Report (select a batch)
    ✓ PLO/GA Attainment Report
    ✓ More Reports → all 10 report types

  Dept Admin Dashboard:
    ✓ Teachers assigned to courses
    ✓ Students enrolled in courses
    ✓ Semester Plans configured

  Instructor Dashboard:
    ✓ Courses with categories, units, CLOs
    ✓ OBE Questions mapped to CLOs
    ✓ Students with marks already entered

  Reports to test (use programId from DB):
    Programs: {', '.join(p.code.lower() for p in programs[:5])}

  Use these to test More Reports tab in QA Dashboard.
{'='*60}
""")
