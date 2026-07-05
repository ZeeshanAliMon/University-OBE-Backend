"""
seed_reports_data — layers a full realistic university semester on top of `seed`.

Run `python manage.py seed` first, then this command.
Safe to re-run — fully idempotent (get_or_create everywhere).

What this creates:
  - 3 extra instructors (Computing x2, Business x1)
  - 13 InstructorCourse records across Computing + Business
  - 4 CLOs per course, mapped to department GAs
  - Full marks structure: Assignments(3), Quizzes(3), Mid Term(1), Final(1)
  - 25-30 students per course with realistic marks (ability-based spread)
  - OBE question marks for CLO attainment reports
  - All frontend_ids match InstructorCourseView formula exactly
"""
import random
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from django.conf import settings as django_settings
from core.models import (
    User, Department, Program, GraduateAttribute,
    Course, InstructorProfile, CourseAssignment,
    InstructorCourse, CLO, MarksCategory, UnitItem,
    OBEQuestion, AdmissionStudent, CourseStudent,
    StudentMark, OBEStudentMark, GradeScale,
)

random.seed(42)

FIRST_NAMES = [
    'Ahmed','Ali','Hamza','Bilal','Usman','Zain','Hassan','Omar','Faisal',
    'Tariq','Imran','Kashif','Waqas','Adeel','Asad','Kamran','Farhan','Talha',
    'Fatima','Ayesha','Zainab','Sana','Mahnoor','Hira','Iqra','Amna','Sadia',
    'Rabia','Mariam','Nadia','Anum','Sidra','Zoya','Areeba','Eman','Laiba',
    'Mishal','Noor','Rimsha','Sara','Mehwish','Khadija','Hafsa','Maryam',
]
LAST_NAMES = [
    'Khan','Ali','Ahmed','Malik','Hussain','Raza','Tariq','Sheikh','Qureshi',
    'Baig','Siddiqui','Farooq','Chaudhry','Abbasi','Butt','Awan','Javed',
    'Iqbal','Rashid','Saeed','Aslam','Akhtar','Yousaf','Mirza','Hashmi',
]

ACADEMIC_YEAR = 'Fall-2024'

# (course_code, prog_slug, dept_slug, instructor_emp_id, semester)
COURSES_TO_RUN = [
    # Computing — Dr Ali (INS-CS-001)
    ('CMC111', 'bscs', 'computing', 'INS-CS-001', '1st'),
    ('CMC112', 'bscs', 'computing', 'INS-CS-001', '2nd'),
    ('CMC251', 'bscs', 'computing', 'INS-CS-001', '3rd'),
    # Computing — Dr Fatima (INS-CS-002)
    ('CMC331', 'bscs', 'computing', 'INS-CS-002', '5th'),
    ('CMC362', 'bscs', 'computing', 'INS-CS-002', '6th'),
    ('CMC241', 'bsse', 'computing', 'INS-CS-002', '4th'),
    # Computing — Dr Hina (INS-CS-003) — new instructor
    ('CMC381', 'bsai', 'computing', 'INS-CS-003', '6th'),
    ('CSC479', 'bsai', 'computing', 'INS-CS-003', '7th'),
    ('CMC371', 'bscs', 'computing', 'INS-CS-003', '5th'),
    # Business — Dr Usman (INS-BIZ-001)
    ('BUS101', 'bba',  'business',  'INS-BIZ-001', '1st'),
    ('MGT331', 'bba',  'business',  'INS-BIZ-001', '6th'),
    # Business — Dr Omar (INS-BIZ-002) — new instructor
    ('ACC121', 'bba',  'business',  'INS-BIZ-002', '2nd'),
    ('FIN311', 'bsaf', 'business',  'INS-BIZ-002', '5th'),
]

NEW_INSTRUCTORS = [
    # email, first, last, dept_slug, emp_id, designation
    ('hina.yousaf@iqra.edu.pk',  'Hina', 'Yousaf', 'computing', 'INS-CS-003',  'Assistant Professor'),
    ('omar.farooq@iqra.edu.pk',  'Omar', 'Farooq', 'business',  'INS-BIZ-002', 'Lecturer'),
]

CATEGORY_DEFS = [
    # (name, percentage, units, total_marks_each)
    ('Assignments', 20, 3, 10),
    ('Quizzes',     15, 3, 10),
    ('Mid Term',    25, 1, 30),
    ('Final',       40, 1, 50),
]

# Students per program pool — each entry is (reg_no_prefix, dept_slug)
PROGRAM_POOLS = {
    'bscs': ('FA24-BSCS', 'computing'),
    'bsse': ('FA24-BSSE', 'computing'),
    'bsai': ('FA24-BSAI', 'computing'),
    'bba':  ('FA24-BBA',  'business'),
    'bsaf': ('FA24-BSAF', 'business'),
}


def _name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def _ability():
    """Returns a float 0-1 skewed toward 0.6-0.85 (realistic university spread)."""
    return min(1.0, max(0.1, random.betavariate(5, 2)))


class Command(BaseCommand):
    help = (
        'Layers a full realistic semester on top of `seed`. '
        'Creates instructors, courses, 25-30 students each with '
        'complete marks and OBE data. Run `seed` first. Idempotent.'
    )

    def handle(self, *args, **kwargs):
        if not Department.objects.exists():
            self.stdout.write(self.style.ERROR(
                'No departments — run `python manage.py seed` first.'
            ))
            return

        self.stdout.write('🌱  Seeding realistic report data...\n')

        depts    = {d.dept_id: d for d in Department.objects.all()}
        progs    = {p.code.lower(): p for p in Program.objects.all()}
        courses  = {c.code: c for c in Course.objects.all()}
        gas_dept = {}
        for ga in GraduateAttribute.objects.select_related('department'):
            gas_dept.setdefault(ga.department.dept_id, []).append(ga)

        # ── Ensure instructors exist ──────────────────────────────────────────
        instructors = {p.employee_id: p
                       for p in InstructorProfile.objects.select_related('user')}

        for email, first, last, dept_slug, emp_id, designation in NEW_INSTRUCTORS:
            if emp_id not in instructors:
                user, _ = User.objects.get_or_create(
                    username=email,
                    defaults=dict(
                        email=email, first_name=first, last_name=last,
                        role='instructor',
                        password=make_password(django_settings.DEFAULT_TEMP_PASSWORD),
                        must_change_password=True, is_active=True,
                    )
                )
                profile, _ = InstructorProfile.objects.get_or_create(
                    user=user,
                    defaults=dict(
                        department=depts[dept_slug],
                        employee_id=emp_id,
                        designation=designation,
                    )
                )
                instructors[emp_id] = profile
                self.stdout.write(f'  + Instructor: {first} {last} ({emp_id})')

        self.stdout.write(f'  ✓ Instructors ready ({len(instructors)} total)\n')

        # ── Build student pools per program ───────────────────────────────────
        # 35 students per program — enough to give every course a different
        # 25-30 student subset so rosters look distinct.
        student_pools = {}
        reg_counter   = 2000
        for prog_slug, (prefix, dept_slug) in PROGRAM_POOLS.items():
            if prog_slug in student_pools:
                continue
            pool = []
            prog = progs.get(prog_slug)
            dept = depts.get(dept_slug)
            if not prog or not dept:
                continue
            for _ in range(35):
                reg_counter += 1
                reg_no = f"{prefix}-{reg_counter:04d}"
                name   = _name()
                AdmissionStudent.objects.get_or_create(
                    reg_no=reg_no,
                    defaults=dict(
                        name=name, department=dept, program=prog,
                        batch=random.choice(['Fall', 'Spring']),
                        semester=random.choice(['1st','2nd','3rd','4th','5th','6th']),
                    )
                )
                pool.append((reg_no, name, _ability()))
            student_pools[prog_slug] = pool

        total_students = sum(len(v) for v in student_pools.values())
        self.stdout.write(f'  ✓ Student pools: {total_students} admission students across '
                          f'{len(student_pools)} programs\n')

        # ── Create InstructorCourses ──────────────────────────────────────────
        courses_created = 0
        students_enrolled = 0
        marks_written = 0

        for course_code, prog_slug, dept_slug, emp_id, semester in COURSES_TO_RUN:
            course   = courses.get(course_code)
            program  = progs.get(prog_slug)
            profile  = instructors.get(emp_id)
            dept     = depts.get(dept_slug)

            if not all([course, program, profile, dept]):
                self.stdout.write(self.style.WARNING(
                    f'  ⚠ Skipping {course_code} — missing '
                    f'course={bool(course)} prog={bool(program)} '
                    f'instructor={bool(profile)}'
                ))
                continue

            # frontend_id must match InstructorCourseView formula exactly
            prog_suffix = program.code.lower()
            term_suffix = f"-{ACADEMIC_YEAR.lower().replace(' ', '')}"
            frontend_id = (
                f"course-assigned-{course_code}-{emp_id}"
                f"-{prog_suffix}{term_suffix}"
            )

            CourseAssignment.objects.get_or_create(
                instructor=profile, course=course,
                program=program, academic_year=ACADEMIC_YEAR,
            )

            ic, ic_created = InstructorCourse.objects.get_or_create(
                instructor=profile,
                frontend_id=frontend_id,
                defaults=dict(
                    code=course_code,
                    title=course.title,
                    course_type='Theory',
                    department=dept,
                    program=program,
                    credit_hours=course.credit_hours or 3,
                    clo_count=4,
                    selected_grading_system='ready1',
                    semester=semester,
                    academic_year=ACADEMIC_YEAR,
                )
            )

            if not ic_created:
                self.stdout.write(f'  → {course_code} ({emp_id}) already exists, skipping')
                continue

            courses_created += 1

            # ── Grade scale ───────────────────────────────────────────────────
            for order, (grade, min_pct, pts) in enumerate([
                ('A',90,4.0),('A-',85,3.7),('B+',80,3.3),('B',75,3.0),
                ('B-',70,2.7),('C+',65,2.3),('C',60,2.0),('C-',55,1.7),
                ('D',50,1.0),('F',0,0.0),
            ]):
                GradeScale.objects.create(
                    course=ic, grade=grade,
                    min_percentage=min_pct, points=pts, order=order,
                )

            # ── CLOs ──────────────────────────────────────────────────────────
            dept_gas = gas_dept.get(dept_slug, [])
            chosen_gas = random.sample(dept_gas, min(4, len(dept_gas))) if dept_gas else []
            clos = []
            clo_descriptions = [
                f'Understand and explain core concepts of {course.title}.',
                f'Apply principles of {course.title} to solve practical problems.',
                f'Analyse complex scenarios in the context of {course.title}.',
                f'Evaluate and synthesize solutions using {course.title} techniques.',
            ]
            for i, ga in enumerate(chosen_gas[:4], start=1):
                clo = CLO.objects.create(
                    course=ic,
                    code=f'CLO-{i}',
                    description=clo_descriptions[i - 1],
                    mapped_ga=ga,
                    order=i,
                )
                clos.append(clo)

            clo_codes = [c.code for c in clos] if clos else ['CLO-1']

            # ── Marks categories + unit items ─────────────────────────────────
            unit_map = {}   # (cat_name, unit_no) → UnitItem
            q_map    = {}   # (cat_name, unit_no) → OBEQuestion

            for cat_order, (cat_name, pct, n_units, max_per_unit) in enumerate(CATEGORY_DEFS):
                cat = MarksCategory.objects.create(
                    course=ic, name=cat_name,
                    percentage=pct, units=n_units, order=cat_order,
                )
                unit_weight = round(100.0 / n_units, 1) if n_units else 100.0
                for unit_no in range(1, n_units + 1):
                    mapped = random.sample(clo_codes, k=min(2, len(clo_codes)))
                    ui = UnitItem.objects.create(
                        category=cat,
                        unit_no=unit_no,
                        total_marks=max_per_unit,
                        passing=max_per_unit // 2,
                        weightage=unit_weight,
                        mapped_clos=mapped,
                    )
                    unit_map[(cat_name, unit_no)] = ui

                    # One OBE question per unit item
                    q = OBEQuestion.objects.create(
                        course=ic,
                        frontend_id=f'{frontend_id}-{cat_name.lower().replace(" ","_")}-u{unit_no}',
                        unit_item=ui,
                        category_name=cat_name,
                        unit_no=unit_no,
                        question_name=f'{cat_name} Unit {unit_no}',
                        max_marks=max_per_unit,
                        mapped_clos=mapped,
                        order=cat_order * 10 + unit_no,
                    )
                    q_map[(cat_name, unit_no)] = q

            # ── Enroll students and write marks ───────────────────────────────
            pool      = student_pools.get(prog_slug, [])
            class_sz  = min(random.randint(25, 30), len(pool))
            roster    = random.sample(pool, class_sz) if pool else []

            for reg_no, name, ability in roster:
                cs = CourseStudent.objects.create(
                    course=ic, reg_no=reg_no, name=name,
                )
                students_enrolled += 1

                for (cat_name, unit_no), ui in unit_map.items():
                    noise = random.uniform(-0.12, 0.08)
                    frac  = max(0.05, min(1.0, ability + noise))
                    score = round(ui.total_marks * frac, 1)
                    StudentMark.objects.create(
                        student=cs, unit_item=ui, score=score,
                    )
                    marks_written += 1

                for (cat_name, unit_no), q in q_map.items():
                    noise  = random.uniform(-0.12, 0.08)
                    frac   = max(0.05, min(1.0, ability + noise))
                    q_score = round(q.max_marks * frac, 1)
                    OBEStudentMark.objects.create(
                        student=cs, question=q, score=q_score,
                    )
                    marks_written += 1

            self.stdout.write(
                f'  ✓ {course_code:<10} instructor={emp_id:<12} '
                f'students={len(roster):>2}  marks={len(roster) * (len(unit_map) + len(q_map))}'
            )

        self.stdout.write(self.style.SUCCESS(f'''
✅  Done!
   New InstructorCourses : {courses_created}
   Students enrolled     : {students_enrolled}
   Mark rows written     : {marks_written}

   InstructorCourses total : {InstructorCourse.objects.count()}
   AdmissionStudents total : {AdmissionStudent.objects.count()}
   CourseStudent rows      : {CourseStudent.objects.count()}
   StudentMark rows        : {StudentMark.objects.count()}
   OBEStudentMark rows     : {OBEStudentMark.objects.count()}

Instructor logins (password: {django_settings.DEFAULT_TEMP_PASSWORD}):
   ali.hassan@iqra.edu.pk    → INS-CS-001  (Computing)
   fatima.malik@iqra.edu.pk  → INS-CS-002  (Computing)
   hina.yousaf@iqra.edu.pk   → INS-CS-003  (Computing)  ← new
   usman.sheikh@iqra.edu.pk  → INS-BIZ-001 (Business)
   omar.farooq@iqra.edu.pk   → INS-BIZ-002 (Business)  ← new

QA reports:
   qa.computing@iqra.edu.pk / qapass123  → programId=bscs, bsse, bsai
   qa.business@iqra.edu.pk  / qapass123  → programId=bba, bsaf
'''))
