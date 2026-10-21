"""
OBE System — Test Data Seed Script
===================================
Run from the project root:
    python manage.py shell < seed_test_data.py
OR:
    python manage.py shell -c "exec(open('seed_test_data.py').read())"

Creates:
  - 2 Departments
  - 2 Programs per department (4 total)
  - Graduate Attributes per department
  - Program Objectives + PO-GA mappings
  - 1 QA user
  - 1 Dept Admin per department (2 total)
  - 2 Instructors per department (4 total)
  - 1 Admission Officer per department (2 total)
  - 5 Courses per program (20 total), with subtype
  - Semester Plans (8 semesters per program)
  - AdmissionStudents (10 per program = 40 total)
  - CourseAssignments (instructor → course)
  - InstructorCourse with CLOs, MarksCategories, UnitItems
  - CourseStudents with sample marks

All passwords: Test@1234
"""

import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'obe_system.settings')

from django.contrib.auth import get_user_model
from core.models import (
    Department, Program, ProgramObjective, GraduateAttribute, POGAMapping,
    QAProfile, InstructorProfile, DeptAdminProfile, AdmissionProfile,
    Student, AdmissionStudent,
    Course, GraduateAttribute, MarksCategory, UnitItem,
    InstructorCourse, CLO, CourseAssignment, CourseStudent, StudentMark,
    SemesterPlan,
)

User = get_user_model()
PASSWORD = "Test@1234"


def make_user(username, email, first_name, last_name, role):
    u, created = User.objects.get_or_create(username=username, defaults={
        'email': email,
        'first_name': first_name,
        'last_name': last_name,
        'role': role,
    })
    if created:
        u.set_password(PASSWORD)
        u.save()
        print(f"  ✓ Created user: {email} [{role}]")
    else:
        print(f"  – Skipped existing user: {email}")
    return u


# ─── 1. Departments ───────────────────────────────────────────────────────────
print("\n[1] Departments")

def get_or_create_dept(dept_id, name, vision, mission):
    # Try by dept_id first
    try:
        d, created = Department.objects.get_or_create(
            dept_id=dept_id,
            defaults={'name': name, 'vision': vision, 'mission': mission}
        )
        return d
    except Exception:
        pass
    # Fallback: already exists with this name under a different dept_id
    try:
        return Department.objects.get(name=name)
    except Department.DoesNotExist:
        pass
    # Last resort: use any existing dept
    existing = Department.objects.first()
    if existing:
        print(f"  ⚠ Could not create dept '{name}', using existing: {existing.name}")
        return existing
    raise Exception(f"No departments found and could not create '{name}'")

dept_cs = get_or_create_dept(
    'computing',
    'Department of Computing',
    'To be a leading computing department producing world-class graduates.',
    'To provide quality education in computing sciences through OBE.',
)
print(f"  ✓ {dept_cs.name}")

dept_bus = get_or_create_dept(
    'business',
    'Department of Business Administration',
    'To cultivate ethical, innovative business leaders.',
    'To deliver outcome-based business education aligned with industry needs.',
)
print(f"  ✓ {dept_bus.name}")


# ─── 2. Programs ──────────────────────────────────────────────────────────────
print("\n[2] Programs")

prog_bscs, _ = Program.objects.get_or_create(
    code='BSCS',
    defaults={
        'name': 'Bachelor of Science in Computer Science',
        'department': dept_cs,
        'vision': 'Produce graduates who lead innovation in computing.',
        'mission': 'Deliver rigorous CS education with OBE framework.',
    }
)
print(f"  ✓ {prog_bscs.code}")

prog_bsse, _ = Program.objects.get_or_create(
    code='BSSE',
    defaults={
        'name': 'Bachelor of Science in Software Engineering',
        'department': dept_cs,
        'vision': 'Produce globally competitive software engineers.',
        'mission': 'Develop engineering skills through project-based OBE learning.',
    }
)
print(f"  ✓ {prog_bsse.code}")

prog_bba, _ = Program.objects.get_or_create(
    code='BBA',
    defaults={
        'name': 'Bachelor of Business Administration',
        'department': dept_bus,
        'vision': 'Develop business leaders for the modern world.',
        'mission': 'Provide outcome-based business education.',
    }
)
print(f"  ✓ {prog_bba.code}")

prog_mba, _ = Program.objects.get_or_create(
    code='MBA',
    defaults={
        'name': 'Master of Business Administration',
        'department': dept_bus,
        'vision': 'Cultivate strategic thinkers and entrepreneurs.',
        'mission': 'Deliver advanced business education through OBE.',
    }
)
print(f"  ✓ {prog_mba.code}")


# ─── 3. Graduate Attributes ───────────────────────────────────────────────────
print("\n[3] Graduate Attributes")

cs_gas_data = [
    ('GA1-CS', 'Engineering Knowledge',    'Apply knowledge of computing fundamentals.'),
    ('GA2-CS', 'Problem Analysis',         'Identify and formulate computing problems.'),
    ('GA3-CS', 'Design/Development',       'Design solutions for complex computing problems.'),
    ('GA4-CS', 'Investigation',            'Conduct research and investigate complex problems.'),
    ('GA5-CS', 'Modern Tool Usage',        'Use modern computing tools and techniques.'),
    ('GA6-CS', 'Ethics',                   'Apply ethical principles in professional practice.'),
    ('GA7-CS', 'Communication',            'Communicate effectively in professional contexts.'),
]

bus_gas_data = [
    ('GA1-BUS', 'Business Knowledge',      'Apply core business and management concepts.'),
    ('GA2-BUS', 'Critical Thinking',       'Analyse and evaluate business scenarios.'),
    ('GA3-BUS', 'Leadership',              'Lead teams and manage resources effectively.'),
    ('GA4-BUS', 'Ethical Practice',        'Demonstrate ethical conduct in business.'),
    ('GA5-BUS', 'Communication',           'Communicate business ideas clearly.'),
]

cs_gas = []
for ga_id, name, desc in cs_gas_data:
    ga, _ = GraduateAttribute.objects.get_or_create(
        ga_id=ga_id,
        defaults={'name': name, 'description': desc, 'department': dept_cs}
    )
    cs_gas.append(ga)
    print(f"  ✓ {ga_id}: {name}")

bus_gas = []
for ga_id, name, desc in bus_gas_data:
    ga, _ = GraduateAttribute.objects.get_or_create(
        ga_id=ga_id,
        defaults={'name': name, 'description': desc, 'department': dept_bus}
    )
    bus_gas.append(ga)
    print(f"  ✓ {ga_id}: {name}")


# ─── 4. Program Objectives + PO-GA Mappings ───────────────────────────────────
print("\n[4] Program Objectives")

cs_pos = [
    ('PO1', 'Graduates will demonstrate strong foundations in computing theory and practice.'),
    ('PO2', 'Graduates will analyse and solve complex real-world computing problems.'),
    ('PO3', 'Graduates will design and develop effective software systems.'),
    ('PO4', 'Graduates will apply ethical and professional standards.'),
]
bus_pos = [
    ('PO1', 'Graduates will demonstrate mastery of core business disciplines.'),
    ('PO2', 'Graduates will think critically and solve business challenges.'),
    ('PO3', 'Graduates will lead and manage organizations effectively.'),
    ('PO4', 'Graduates will uphold ethical business practices.'),
]

cs_po_objs = []
for code, desc in cs_pos:
    for prog in [prog_bscs, prog_bsse]:
        po, _ = ProgramObjective.objects.get_or_create(
            program=prog, code=code,
            defaults={'description': desc}
        )
        cs_po_objs.append(po)
        print(f"  ✓ {prog.code} {code}")

bus_po_objs = []
for code, desc in bus_pos:
    for prog in [prog_bba, prog_mba]:
        po, _ = ProgramObjective.objects.get_or_create(
            program=prog, code=code,
            defaults={'description': desc}
        )
        bus_po_objs.append(po)
        print(f"  ✓ {prog.code} {code}")

# PO → GA Mappings
print("\n[4b] PO-GA Mappings")
mappings = [
    # (program, po_code, ga_id)
    (prog_bscs, 'PO1', 'GA1-CS'),
    (prog_bscs, 'PO2', 'GA2-CS'),
    (prog_bscs, 'PO3', 'GA3-CS'),
    (prog_bscs, 'PO4', 'GA6-CS'),
    (prog_bsse, 'PO1', 'GA1-CS'),
    (prog_bsse, 'PO2', 'GA2-CS'),
    (prog_bsse, 'PO3', 'GA3-CS'),
    (prog_bsse, 'PO4', 'GA6-CS'),
    (prog_bba,  'PO1', 'GA1-BUS'),
    (prog_bba,  'PO2', 'GA2-BUS'),
    (prog_bba,  'PO3', 'GA3-BUS'),
    (prog_bba,  'PO4', 'GA4-BUS'),
    (prog_mba,  'PO1', 'GA1-BUS'),
    (prog_mba,  'PO2', 'GA2-BUS'),
    (prog_mba,  'PO3', 'GA3-BUS'),
    (prog_mba,  'PO4', 'GA4-BUS'),
]
for prog, po_code, ga_id in mappings:
    try:
        po = ProgramObjective.objects.get(program=prog, code=po_code)
        ga = GraduateAttribute.objects.get(ga_id=ga_id)
        POGAMapping.objects.get_or_create(program_objective=po, graduate_attribute=ga)
        print(f"  ✓ {prog.code} {po_code} → {ga_id}")
    except Exception as e:
        print(f"  ✗ {prog.code} {po_code} → {ga_id}: {e}")


# ─── 5. Users ─────────────────────────────────────────────────────────────────
print("\n[5] Users & Profiles")

# QA User
qa_user = make_user('qa_officer', 'qa@iqra.edu.pk', 'Ayesha', 'Siddiqui', 'qa')
QAProfile.objects.get_or_create(
    user=qa_user,
    defaults={'department': dept_cs, 'employee_id': 'QA-001'}
)

# Dept Admins
da_cs_user = make_user('da_computing', 'deptadmin.cs@iqra.edu.pk', 'Zeeshan', 'Ali', 'dept_admin')
DeptAdminProfile.objects.get_or_create(
    user=da_cs_user,
    defaults={'department': dept_cs, 'employee_id': 'DA-CS-001'}
)

da_bus_user = make_user('da_business', 'deptadmin.bus@iqra.edu.pk', 'Fatima', 'Khan', 'dept_admin')
DeptAdminProfile.objects.get_or_create(
    user=da_bus_user,
    defaults={'department': dept_bus, 'employee_id': 'DA-BUS-001'}
)

# Admission Officers
adm_cs_user = make_user('admission_cs', 'admission.cs@iqra.edu.pk', 'Usman', 'Raza', 'admission')
AdmissionProfile.objects.get_or_create(
    user=adm_cs_user,
    defaults={'department': dept_cs, 'employee_id': 'ADM-CS-001'}
)

adm_bus_user = make_user('admission_bus', 'admission.bus@iqra.edu.pk', 'Sana', 'Malik', 'admission')
AdmissionProfile.objects.get_or_create(
    user=adm_bus_user,
    defaults={'department': dept_bus, 'employee_id': 'ADM-BUS-001'}
)

# Instructors
inst_data = [
    ('inst_ahmed',   'ahmed@iqra.edu.pk',   'Ahmed',   'Hassan',   dept_cs,  'INST-CS-001', 'Assistant Professor'),
    ('inst_sara',    'sara@iqra.edu.pk',     'Sara',    'Qureshi',  dept_cs,  'INST-CS-002', 'Lecturer'),
    ('inst_bilal',   'bilal@iqra.edu.pk',    'Bilal',   'Chaudhry', dept_cs,  'INST-CS-003', 'Associate Professor'),
    ('inst_nadia',   'nadia@iqra.edu.pk',    'Nadia',   'Farooq',   dept_bus, 'INST-BUS-001', 'Assistant Professor'),
    ('inst_tariq',   'tariq@iqra.edu.pk',    'Tariq',   'Mehmood',  dept_bus, 'INST-BUS-002', 'Lecturer'),
]

instructors = {}
for username, email, first, last, dept, emp_id, designation in inst_data:
    u = make_user(username, email, first, last, 'instructor')
    prof, _ = InstructorProfile.objects.get_or_create(
        user=u,
        defaults={'department': dept, 'employee_id': emp_id, 'designation': designation}
    )
    instructors[username] = prof


# ─── 6. Courses ───────────────────────────────────────────────────────────────
print("\n[6] Courses")

courses_data = [
    # (code, title, type, subtype, dept, program, gas)
    # BSCS Courses
    ('CS101', 'Introduction to Programming',       'core',     'theory', dept_cs, prog_bscs, ['GA1-CS', 'GA2-CS']),
    ('CS201', 'Data Structures',                   'core',     'theory', dept_cs, prog_bscs, ['GA1-CS', 'GA2-CS']),
    ('CS202', 'Data Structures Lab',               'core',     'lab',    dept_cs, prog_bscs, ['GA1-CS', 'GA3-CS']),
    ('CS301', 'Database Systems',                  'core',     'theory', dept_cs, prog_bscs, ['GA2-CS', 'GA3-CS']),
    ('CS401', 'Software Engineering',              'core',     'theory', dept_cs, prog_bscs, ['GA3-CS', 'GA6-CS']),
    ('CS402', 'Artificial Intelligence',           'elective', 'theory', dept_cs, prog_bscs, ['GA2-CS', 'GA4-CS']),
    # BSSE Courses
    ('SE101', 'Intro to Software Engineering',     'core',     'theory', dept_cs, prog_bsse, ['GA1-CS', 'GA2-CS']),
    ('SE201', 'Object Oriented Programming',       'core',     'theory', dept_cs, prog_bsse, ['GA1-CS', 'GA3-CS']),
    ('SE202', 'OOP Lab',                           'core',     'lab',    dept_cs, prog_bsse, ['GA1-CS', 'GA5-CS']),
    ('SE301', 'Software Design Patterns',          'core',     'theory', dept_cs, prog_bsse, ['GA3-CS', 'GA5-CS']),
    ('SE401', 'Software Project Management',       'core',     'theory', dept_cs, prog_bsse, ['GA3-CS', 'GA6-CS']),
    # BBA Courses
    ('BBA101', 'Principles of Management',         'core',     'theory', dept_bus, prog_bba, ['GA1-BUS', 'GA2-BUS']),
    ('BBA201', 'Financial Accounting',             'core',     'theory', dept_bus, prog_bba, ['GA1-BUS', 'GA2-BUS']),
    ('BBA301', 'Marketing Management',             'core',     'theory', dept_bus, prog_bba, ['GA2-BUS', 'GA3-BUS']),
    ('BBA401', 'Business Ethics',                  'core',     'theory', dept_bus, prog_bba, ['GA4-BUS', 'GA5-BUS']),
    ('BBA402', 'Entrepreneurship',                 'elective', 'theory', dept_bus, prog_bba, ['GA3-BUS', 'GA4-BUS']),
    # MBA Courses
    ('MBA101', 'Advanced Management Theory',       'core',     'theory', dept_bus, prog_mba, ['GA1-BUS', 'GA2-BUS']),
    ('MBA201', 'Strategic Management',             'core',     'theory', dept_bus, prog_mba, ['GA2-BUS', 'GA3-BUS']),
    ('MBA301', 'Corporate Finance',                'core',     'theory', dept_bus, prog_mba, ['GA1-BUS', 'GA2-BUS']),
    ('MBA401', 'Business Research Methods',        'core',     'theory', dept_bus, prog_mba, ['GA2-BUS', 'GA4-BUS']),
]

course_objs = {}
for code, title, ctype, subtype, dept, prog, ga_ids in courses_data:
    course, created = Course.objects.get_or_create(
        code=code, department=dept, program=prog,
        defaults={
            'title': title,
            'type': ctype,
            'subtype': subtype,
            'credit_hours': 1 if 'lab' in title.lower() or subtype == 'lab' else 3,
        }
    )
    if created:
        gas = GraduateAttribute.objects.filter(ga_id__in=ga_ids)
        course.mapped_gas.set(gas)
        print(f"  ✓ {code}: {title} [{subtype}]")
    else:
        print(f"  – Skipped existing course: {code}")
    course_objs[code] = course


# ─── 7. Semester Plans ────────────────────────────────────────────────────────
print("\n[7] Semester Plans")

semester_plans = {
    prog_bscs: {
        '1st': ['CS101'],
        '2nd': ['CS201', 'CS202'],
        '3rd': ['CS301'],
        '4th': ['CS401'],
        '5th': ['CS402'],
        '6th': [],
        '7th': [],
        '8th': [],
    },
    prog_bsse: {
        '1st': ['SE101'],
        '2nd': ['SE201', 'SE202'],
        '3rd': ['SE301'],
        '4th': ['SE401'],
        '5th': [],
        '6th': [],
        '7th': [],
        '8th': [],
    },
    prog_bba: {
        '1st': ['BBA101'],
        '2nd': ['BBA201'],
        '3rd': ['BBA301'],
        '4th': ['BBA401'],
        '5th': ['BBA402'],
        '6th': [],
        '7th': [],
        '8th': [],
    },
    prog_mba: {
        '1st': ['MBA101'],
        '2nd': ['MBA201'],
        '3rd': ['MBA301'],
        '4th': ['MBA401'],
        '5th': [],
        '6th': [],
        '7th': [],
        '8th': [],
    },
}

da_cs  = DeptAdminProfile.objects.get(user=da_cs_user)
da_bus = DeptAdminProfile.objects.get(user=da_bus_user)

for prog, semesters in semester_plans.items():
    da = da_cs if prog.department == dept_cs else da_bus
    for sem, codes in semesters.items():
        sp, created = SemesterPlan.objects.get_or_create(
            program=prog, semester=sem,
            defaults={'course_codes': codes, 'updated_by': da}
        )
        if created:
            print(f"  ✓ {prog.code} Semester {sem}: {codes}")


# ─── 8. Admission Students ────────────────────────────────────────────────────
print("\n[8] Admission Students")

students_data = []
for prog, dept in [(prog_bscs, dept_cs), (prog_bsse, dept_cs), (prog_bba, dept_bus), (prog_mba, dept_bus)]:
    prefix = prog.code
    batches = ['Fall', 'Spring']
    semesters = ['1st', '2nd', '3rd', '4th']
    count = 0
    for i in range(1, 11):
        reg_no   = f"{prefix}-2024-{i:03d}"
        batch    = batches[i % 2]
        semester = semesters[i % 4]
        s, created = AdmissionStudent.objects.get_or_create(
            reg_no=reg_no,
            defaults={
                'name': f"Student {prefix} {i}",
                'email': f"student{i}.{prefix.lower()}@iqra.edu.pk",
                'department': dept,
                'program': prog,
                'batch': batch,
                'semester': semester,
            }
        )
        if created:
            count += 1
    print(f"  ✓ {prog.code}: {count} students created")


# ─── 9. Course Assignments ────────────────────────────────────────────────────
print("\n[9] Course Assignments")

assignments_data = [
    # (instructor_username, course_code, program, academic_year)
    ('inst_ahmed',  'CS101', prog_bscs, 'Fall-2024'),
    ('inst_ahmed',  'CS201', prog_bscs, 'Fall-2024'),
    ('inst_sara',   'CS202', prog_bscs, 'Fall-2024'),
    ('inst_sara',   'CS301', prog_bscs, 'Fall-2024'),
    ('inst_bilal',  'CS401', prog_bscs, 'Fall-2024'),
    ('inst_ahmed',  'SE101', prog_bsse, 'Fall-2024'),
    ('inst_sara',   'SE201', prog_bsse, 'Fall-2024'),
    ('inst_bilal',  'SE202', prog_bsse, 'Fall-2024'),
    ('inst_nadia',  'BBA101', prog_bba, 'Fall-2024'),
    ('inst_nadia',  'BBA201', prog_bba, 'Fall-2024'),
    ('inst_tariq',  'BBA301', prog_bba, 'Fall-2024'),
    ('inst_nadia',  'MBA101', prog_mba, 'Fall-2024'),
    ('inst_tariq',  'MBA201', prog_mba, 'Fall-2024'),
]

da_cs  = DeptAdminProfile.objects.get(user=da_cs_user)
da_bus = DeptAdminProfile.objects.get(user=da_bus_user)

for inst_username, course_code, prog, academic_year in assignments_data:
    try:
        inst   = instructors[inst_username]
        course = course_objs[course_code]
        da     = da_cs if inst.department == dept_cs else da_bus
        ca, created = CourseAssignment.objects.get_or_create(
            instructor=inst, course=course, program=prog, academic_year=academic_year,
            defaults={'assigned_by': da}
        )
        if created:
            print(f"  ✓ {inst_username} → {course_code} ({prog.code}) [{academic_year}]")
        else:
            print(f"  – Skipped existing: {inst_username} → {course_code}")
    except Exception as e:
        print(f"  ✗ {inst_username} → {course_code}: {e}")


# ─── 10. InstructorCourses with CLOs, Categories, Units, Students, Marks ──────
print("\n[10] Instructor Courses (with CLOs, marks, students)")

def make_instructor_course(inst_username, course_code, prog, academic_year, semester):
    inst   = instructors[inst_username]
    course = course_objs[course_code]
    frontend_id = f"{course_code}-{academic_year}"

    ic, created = InstructorCourse.objects.get_or_create(
        instructor=inst,
        frontend_id=frontend_id,
        defaults={
            'catalog_course': course,
            'course_type': 'Lab' if course.subtype == 'lab' else 'Theory',
            'code': course.code,
            'title': course.title,
            'department': course.department,
            'program': prog,
            'credit_hours': course.credit_hours,
            'clo_count': 3,
            'selected_grading_system': 'ready1',
            'semester': semester,
            'academic_year': academic_year,
            'status': 'active',
        }
    )
    if not created:
        print(f"    – Skipped existing InstructorCourse: {frontend_id}")
        return ic

    print(f"    ✓ InstructorCourse: {course_code} [{inst_username}] {academic_year}")

    # CLOs
    gas = list(course.mapped_gas.all())
    clos = []
    for i in range(1, 4):
        ga = gases[i-1] if (gases := gas) and i <= len(gas) else None
        clo, _ = CLO.objects.get_or_create(
            course=ic, code=f"CLO-{i}",
            defaults={
                'description': f"Students will demonstrate competency in {course.title} — Outcome {i}.",
                'mapped_ga': ga,
                'order': i,
            }
        )
        clos.append(clo)

    # MarksCategories on the catalog course (shared across offerings)
    categories_data = [
        ('Assignments', 15.0, 3, 0),
        ('Quizzes',     10.0, 3, 1),
        ('Mid Term',    25.0, 1, 2),
        ('Final Exam',  50.0, 1, 3),
    ]
    cat_objs = []
    for name, pct, units_count, order in categories_data:
        cat, _ = MarksCategory.objects.get_or_create(
            course=course, name=name,
            defaults={'percentage': pct, 'units': units_count, 'order': order}
        )
        cat_objs.append((cat, units_count))

    # UnitItems
    unit_objs = []
    for cat, units_count in cat_objs:
        for u in range(1, units_count + 1):
            clo_codes = [f"CLO-{((u-1) % 3) + 1}"]
            ui, _ = UnitItem.objects.get_or_create(
                category=cat, unit_no=u,
                defaults={
                    'passing': 5,
                    'total_marks': 10,
                    'weightage': round(cat.percentage / units_count, 2),
                    'mapped_clos': clo_codes,
                }
            )
            unit_objs.append(ui)

    # CourseStudents + Marks
    prog_students = AdmissionStudent.objects.filter(program=prog)[:8]
    import random
    random.seed(42)
    for student in prog_students:
        cs, _ = CourseStudent.objects.get_or_create(
            course=ic,
            reg_no=student.reg_no,
            defaults={'name': student.name}
        )
        for ui in unit_objs:
            score = round(random.uniform(4, ui.total_marks), 1)
            StudentMark.objects.get_or_create(
                student=cs,
                unit_item=ui,
                defaults={'score': score}
            )

    return ic


ic_data = [
    ('inst_ahmed',  'CS101',  prog_bscs, 'Fall-2024',   '2nd'),
    ('inst_ahmed',  'CS201',  prog_bscs, 'Fall-2024',   '3rd'),
    ('inst_sara',   'CS202',  prog_bscs, 'Fall-2024',   '3rd'),
    ('inst_sara',   'CS301',  prog_bscs, 'Fall-2024',   '5th'),
    ('inst_bilal',  'CS401',  prog_bscs, 'Fall-2024',   '7th'),
    ('inst_ahmed',  'SE101',  prog_bsse, 'Fall-2024',   '1st'),
    ('inst_nadia',  'BBA101', prog_bba,  'Fall-2024',   '1st'),
    ('inst_nadia',  'BBA201', prog_bba,  'Fall-2024',   '3rd'),
    ('inst_tariq',  'MBA101', prog_mba,  'Fall-2024',   '1st'),
]

for inst_username, course_code, prog, academic_year, semester in ic_data:
    try:
        make_instructor_course(inst_username, course_code, prog, academic_year, semester)
    except Exception as e:
        print(f"  ✗ {inst_username} → {course_code}: {e}")


# ─── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("SEED COMPLETE — Test accounts (password: Test@1234):")
print("="*60)
print(f"  QA Officer       : qa@iqra.edu.pk")
print(f"  Dept Admin (CS)  : deptadmin.cs@iqra.edu.pk")
print(f"  Dept Admin (BUS) : deptadmin.bus@iqra.edu.pk")
print(f"  Instructor 1     : ahmed@iqra.edu.pk")
print(f"  Instructor 2     : sara@iqra.edu.pk")
print(f"  Instructor 3     : bilal@iqra.edu.pk")
print(f"  Instructor 4     : nadia@iqra.edu.pk")
print(f"  Instructor 5     : tariq@iqra.edu.pk")
print(f"  Admission (CS)   : admission.cs@iqra.edu.pk")
print(f"  Admission (BUS)  : admission.bus@iqra.edu.pk")
print(f"\n  Departments: {Department.objects.count()}")
print(f"  Programs   : {Program.objects.count()}")
print(f"  Courses    : {Course.objects.count()}")
print(f"  Students   : {AdmissionStudent.objects.count()}")
print(f"  GAs        : {GraduateAttribute.objects.count()}")
print(f"  InstructorCourses: {InstructorCourse.objects.count()}")
print("="*60)
