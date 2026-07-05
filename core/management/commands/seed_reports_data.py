import random

from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password

from core.models import (
    User, Department, Program, GraduateAttribute, Course,
    InstructorProfile, CourseAssignment, InstructorCourse, CLO,
    MarksCategory, UnitItem, OBEQuestion, AdmissionStudent,
    CourseStudent, StudentMark, OBEStudentMark,
)

# Fixed seed — reproducible data. Re-running this command produces the exact
# same numbers, so reports look the same across resets instead of shifting
# randomly every time someone runs `seed_reports_data` again.
random.seed(42)

FIRST_NAMES = [
    'Ahmed', 'Ali', 'Hamza', 'Bilal', 'Usman', 'Zain', 'Hassan', 'Hussain',
    'Omar', 'Faisal', 'Tariq', 'Imran', 'Kashif', 'Waqas', 'Adeel', 'Asad',
    'Fatima', 'Ayesha', 'Zainab', 'Sana', 'Mahnoor', 'Hira', 'Iqra', 'Amna',
    'Sadia', 'Rabia', 'Mariam', 'Nadia', 'Sana', 'Komal', 'Anum', 'Sidra',
    'Zoya', 'Areeba', 'Eman', 'Laiba', 'Mishal', 'Noor', 'Rimsha', 'Sara',
]
LAST_NAMES = [
    'Khan', 'Ali', 'Ahmed', 'Malik', 'Hussain', 'Raza', 'Tariq', 'Sheikh',
    'Qureshi', 'Baig', 'Siddiqui', 'Farooq', 'Chaudhry', 'Abbasi', 'Butt',
    'Awan', 'Javed', 'Iqbal', 'Rashid', 'Saeed', 'Aslam', 'Akhtar', 'Yousaf',
]

# (course_code, program_slug, dept_slug, instructor_employee_id, semester)
COURSES_TO_ACTIVATE = [
    ('CMC111', 'bscs', 'computing', 'INS-CS-001',  '1st'),
    ('CMC112', 'bscs', 'computing', 'INS-CS-001',  '2nd'),
    ('CMC251', 'bscs', 'computing', 'INS-CS-002',  '3rd'),
    ('CMC331', 'bscs', 'computing', 'INS-CS-002',  '5th'),
    ('CMC362', 'bscs', 'computing', 'INS-CS-003',  '6th'),
    ('CMC381', 'bsai', 'computing', 'INS-CS-003',  '6th'),
    ('CSC479', 'bsai', 'computing', 'INS-CS-001',  '7th'),
    ('CMC241', 'bsse', 'computing', 'INS-CS-002',  '4th'),
    ('BUS101', 'bba',  'business',  'INS-BIZ-001', '1st'),
    ('MKT111', 'bba',  'business',  'INS-BIZ-001', '2nd'),
    ('ACC121', 'bba',  'business',  'INS-BIZ-002', '2nd'),
    ('MGT331', 'bba',  'business',  'INS-BIZ-002', '6th'),
    ('FIN311', 'bsaf', 'business',  'INS-BIZ-001', '5th'),
]

NEW_INSTRUCTORS = [
    # username, first, last, email, dept_slug, employee_id, designation
    ('dr_hina', 'Hina', 'Yousaf', 'hina.yousaf@iqra.edu.pk', 'computing', 'INS-CS-003', 'Assistant Professor'),
    ('dr_omar', 'Omar', 'Farooq', 'omar.farooq@iqra.edu.pk', 'business',  'INS-BIZ-002', 'Lecturer'),
]

ACADEMIC_YEARS = ['Fall-2024', 'Spring-2025', 'Fall-2025']

CATEGORY_DEFS = [
    # name, percentage, units, max_marks_per_unit
    ('Quizzes',     15, 3, 10),
    ('Assignments', 20, 3, 10),
    ('Mid Term',    25, 1, 30),
    ('Final',       40, 1, 50),
]


class Command(BaseCommand):
    help = (
        'Layers realistic bulk data on top of `seed`: many more instructor '
        'courses, CLOs, students, and marks, so PO/GA attainment, cohort '
        'comparison, instructor performance, and gap analysis reports have '
        'enough real data to look meaningful instead of flat/trivial. '
        'Idempotent — safe to re-run; run `seed` first.'
    )

    def handle(self, *args, **kwargs):
        if not Department.objects.exists():
            self.stdout.write(self.style.ERROR(
                'No departments found — run `python manage.py seed` first.'
            ))
            return

        self.stdout.write('🌱  Adding realistic report data...')

        depts = {d.dept_id: d for d in Department.objects.all()}
        progs = {p.code.lower(): p for p in Program.objects.all()}
        gas_by_dept = {}
        for ga in GraduateAttribute.objects.select_related('department'):
            gas_by_dept.setdefault(ga.department.dept_id, []).append(ga)

        # ── Extra instructors ────────────────────────────────────────────────
        # Keyed by employee_id, not username — seed.py sets username=email,
        # not a friendly handle, so that's the only reliable stable key here.
        instructors = {}
        for p in InstructorProfile.objects.select_related('user'):
            instructors[p.employee_id] = p
        for username, first, last, email, dept_slug, emp_id, designation in NEW_INSTRUCTORS:
            user, created = User.objects.get_or_create(
                username=email,
                defaults=dict(
                    email=email, first_name=first, last_name=last, role='instructor',
                    password=make_password('instpass123'), is_active=True,
                )
            )
            profile, _ = InstructorProfile.objects.get_or_create(
                user=user,
                defaults=dict(department=depts[dept_slug], employee_id=emp_id, designation=designation)
            )
            instructors[emp_id] = profile
        self.stdout.write(f'  ✓ Instructors ({len(instructors)} total, {len(NEW_INSTRUCTORS)} new)')

        # ── Bulk admission students, spread across programs ─────────────────
        # Generous pool per program so each activated course can enroll a
        # realistic class size (20-30) without reusing the same few names
        # everywhere.
        students_by_program = {}
        reg_counter = 1000  # starts well above the base seed's reg_nos
        for code, prog_slug, dept_slug, _instr, _sem in COURSES_TO_ACTIVATE:
            if prog_slug in students_by_program:
                continue
            prog = progs.get(prog_slug)
            if not prog:
                continue
            batch_students = []
            for _ in range(35):
                reg_counter += 1
                name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
                reg_no = f"BLK-{prog_slug.upper()}-{reg_counter:04d}"
                admission, _ = AdmissionStudent.objects.get_or_create(
                    reg_no=reg_no,
                    defaults=dict(
                        name=name, department=depts[dept_slug], program=prog,
                        batch=random.choice(['Fall', 'Spring']),
                        semester=random.choice(['1st', '2nd', '3rd', '4th', '5th', '6th']),
                    )
                )
                # Per-student "ability" — drives every mark they get across
                # every course, so reports show a believable spread (some
                # consistently strong, some weak, most in the middle) instead
                # of pure random noise with no underlying signal.
                ability = random.betavariate(5, 2)  # skews toward 0.6-0.9, long tail down
                batch_students.append((reg_no, name, ability))
            students_by_program[prog_slug] = batch_students
        total_students = sum(len(v) for v in students_by_program.values())
        self.stdout.write(f'  ✓ Admission Students (+{total_students} across {len(students_by_program)} programs)')

        # ── Activate courses ─────────────────────────────────────────────────
        courses_created = 0
        marks_created = 0
        for code, prog_slug, dept_slug, instr_key, semester in COURSES_TO_ACTIVATE:
            course = Course.objects.filter(code=code).first()
            program = progs.get(prog_slug)
            profile = instructors.get(instr_key)
            if not (course and program and profile):
                self.stdout.write(self.style.WARNING(
                    f'  ⚠ skipping {code} — missing course/program/instructor'
                ))
                continue

            academic_year = random.choice(ACADEMIC_YEARS)
            dept = depts[dept_slug]

            CourseAssignment.objects.get_or_create(
                instructor=profile, course=course, program=program,
                academic_year=academic_year,
            )

            prog_suffix = program.code.lower()
            term_suffix = f"-{academic_year.lower().replace(' ', '')}"
            frontend_id = f"course-assigned-{code}-{profile.employee_id}-{prog_suffix}{term_suffix}"

            ic, ic_created = InstructorCourse.objects.get_or_create(
                instructor=profile, frontend_id=frontend_id,
                defaults=dict(
                    code=code, title=course.title, course_type='Theory',
                    department=dept, program=program, credit_hours=course.credit_hours or 3,
                    clo_count=4, selected_grading_system='ready1',
                    semester=semester, academic_year=academic_year,
                )
            )
            if not ic_created:
                continue  # already generated in a previous run — skip cleanly
            courses_created += 1

            # ── CLOs, mapped to this department's GAs ────────────────────────
            dept_gas = gas_by_dept.get(dept_slug, [])
            chosen_gas = random.sample(dept_gas, min(4, len(dept_gas))) if dept_gas else []
            clos = []
            for i, ga in enumerate(chosen_gas, start=1):
                clo = CLO.objects.create(
                    course=ic, code=f'CLO-{i}',
                    description=f'Apply core concepts of {course.title} relevant to {ga.name.lower()}.',
                    mapped_ga=ga, order=i,
                )
                clos.append(clo)
            clo_codes = [c.code for c in clos] or ['CLO-1']

            # ── Categories, units, questions ─────────────────────────────────
            unit_map = {}
            question_defs = []  # (category, unit_no, max_marks, mapped_clos)
            for order, (cat_name, pct, units, max_marks) in enumerate(CATEGORY_DEFS):
                cat = MarksCategory.objects.create(course=ic, name=cat_name, percentage=pct, units=units, order=order)
                for unit_no in range(1, units + 1):
                    mapped = random.sample(clo_codes, k=min(2, len(clo_codes)))
                    u = UnitItem.objects.create(
                        category=cat, unit_no=unit_no, total_marks=max_marks,
                        passing=max_marks // 2, weightage=round(100 / units, 1),
                        mapped_clos=mapped,
                    )
                    unit_map[(cat_name, unit_no)] = u
                    question_defs.append((cat_name, unit_no, max_marks, mapped))

            q_map = {}
            for i, (cat_name, unit_no, max_marks, mapped) in enumerate(question_defs):
                q = OBEQuestion.objects.create(
                    course=ic, frontend_id=f'{frontend_id}-q{i}',
                    unit_item=unit_map[(cat_name, unit_no)],
                    category_name=cat_name, unit_no=unit_no,
                    question_name=f'{cat_name} {unit_no}', max_marks=max_marks,
                    mapped_clos=mapped, order=i,
                )
                q_map[(cat_name, unit_no)] = q

            # ── Enroll students and generate marks ───────────────────────────
            pool = students_by_program.get(prog_slug, [])
            class_size = min(random.randint(20, 30), len(pool))
            roster = random.sample(pool, class_size) if pool else []
            for reg_no, name, ability in roster:
                cs = CourseStudent.objects.create(course=ic, reg_no=reg_no, name=name)
                for (cat_name, unit_no), unit in unit_map.items():
                    # Score = student's ability × max marks, plus per-item
                    # noise, clipped to a valid range — this is what gives
                    # attainment reports a realistic non-uniform spread
                    # instead of every student scoring identically.
                    noise = random.uniform(-0.15, 0.1)
                    frac = max(0.05, min(1.0, ability + noise))
                    score = round(unit.total_marks * frac, 1)
                    StudentMark.objects.create(student=cs, unit_item=unit, score=score)
                    marks_created += 1

                    q = q_map.get((cat_name, unit_no))
                    if q:
                        q_noise = random.uniform(-0.15, 0.1)
                        q_frac = max(0.05, min(1.0, ability + q_noise))
                        q_score = round(q.max_marks * q_frac, 1)
                        OBEStudentMark.objects.create(student=cs, question=q, score=q_score)
                        marks_created += 1

        self.stdout.write(f'  ✓ Instructor Courses activated (+{courses_created})')
        self.stdout.write(f'  ✓ Marks generated (+{marks_created} rows)')

        self.stdout.write(self.style.SUCCESS('\n✅  Report data ready!'))
        self.stdout.write(f'   Instructor Courses : {InstructorCourse.objects.count()}')
        self.stdout.write(f'   Admission Students : {AdmissionStudent.objects.count()}')
        self.stdout.write(f'   CourseStudent rows : {CourseStudent.objects.count()}')
        self.stdout.write(f'   StudentMark rows   : {StudentMark.objects.count()}')
        self.stdout.write(f'   OBEStudentMark rows: {OBEStudentMark.objects.count()}')
        self.stdout.write('\n  New instructor logins (password: instpass123):')
        self.stdout.write('   hina.yousaf@iqra.edu.pk')
        self.stdout.write('   omar.farooq@iqra.edu.pk')
        self.stdout.write('\n  Try the reports now as qa.computing@iqra.edu.pk / qapass123')
        self.stdout.write('  or qa.business@iqra.edu.pk / qapass123 — programId=BSCS, BSAI, BSSE, BBA, BSAF')
