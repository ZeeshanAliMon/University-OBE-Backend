from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from core.models import (
    User, Department, Program, ProgramObjective, POGAMapping,
    GraduateAttribute, QAProfile, InstructorProfile, Student,
    Course, InstructorCourse, GradeScale, MarksCategory, UnitItem,
    OBEQuestion, CourseStudent, StudentMark, OBEStudentMark,
)


class Command(BaseCommand):
    help = 'Seed the database with placeholder data'

    def handle(self, *args, **kwargs):
        self.stdout.write('🌱  Seeding database ...')

        # ── Clean slate ───────────────────────────────────────────────────────
        OBEStudentMark.objects.all().delete()
        StudentMark.objects.all().delete()
        CourseStudent.objects.all().delete()
        OBEQuestion.objects.all().delete()
        UnitItem.objects.all().delete()
        MarksCategory.objects.all().delete()
        GradeScale.objects.all().delete()
        InstructorCourse.objects.all().delete()
        POGAMapping.objects.all().delete()
        ProgramObjective.objects.all().delete()
        Course.objects.all().delete()
        GraduateAttribute.objects.all().delete()
        Student.objects.all().delete()
        InstructorProfile.objects.all().delete()
        QAProfile.objects.all().delete()
        Program.objects.all().delete()
        Department.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        self.stdout.write('  ✓ Cleared old data')

        # ── Departments ───────────────────────────────────────────────────────
        dept_cs = Department.objects.create(
            slug='computing',
            name='Department of Computing and Technology',
            vision='To be a globally recognized department producing world-class computing professionals.',
            mission='To deliver high-quality computing education grounded in outcome-based learning.',
        )
        dept_biz = Department.objects.create(
            slug='business',
            name='Department of Business Administration',
            vision='To nurture future business leaders who create sustainable value.',
            mission='To provide rigorous, practice-oriented business education.',
        )
        self.stdout.write('  ✓ Departments')

        # ── Programs ──────────────────────────────────────────────────────────
        prog_bscs = Program.objects.create(
            slug='bscs', name='Bachelor of Science in Computer Science',
            code='BSCS', department=dept_cs,
            vision='To produce innovative, ethical CS graduates.',
            mission='To provide rigorous CS foundations and practical skills.',
        )
        prog_bsse = Program.objects.create(
            slug='bsse', name='Bachelor of Science in Software Engineering',
            code='BSSE', department=dept_cs,
            vision='To develop quality software engineers.',
            mission='To instill SE principles, project management, and ethics.',
        )
        prog_bba = Program.objects.create(
            slug='bba', name='Bachelor of Business Administration',
            code='BBA', department=dept_biz,
            vision='To cultivate business leaders with integrity.',
            mission='To deliver a comprehensive business curriculum.',
        )
        prog_mba = Program.objects.create(
            slug='mba', name='Master of Business Administration',
            code='MBA', department=dept_biz,
            vision='To produce strategic thinkers for global challenges.',
            mission='To develop advanced managerial and leadership capabilities.',
        )
        self.stdout.write('  ✓ Programs')

        # ── Graduate Attributes ───────────────────────────────────────────────
        all_gas = {}
        ga_data = [
            ('GA-1',    'Academic Education',      'Apply knowledge of computing and mathematics.',              dept_cs,  prog_bscs),
            ('GA-2',    'Problem Analysis',         'Identify and analyse complex computing problems.',           dept_cs,  prog_bscs),
            ('GA-3',    'Design and Development',   'Design and develop solutions for computing problems.',       dept_cs,  prog_bscs),
            ('GA-4',    'Investigation',            'Investigate complex problems using research methods.',       dept_cs,  prog_bscs),
            ('GA-5',    'Modern Tool Usage',        'Apply modern computing tools and techniques.',               dept_cs,  prog_bscs),
            ('GA-6',    'Ethics',                   'Apply ethical principles and professional responsibilities.',dept_cs,  prog_bscs),
            ('GA-SE-1', 'Engineering Knowledge',    'Apply software engineering principles.',                    dept_cs,  prog_bsse),
            ('GA-SE-2', 'Problem Analysis',         'Identify and analyse complex SE problems.',                 dept_cs,  prog_bsse),
            ('GA-SE-3', 'Design & Architecture',    'Design software architectures meeting requirements.',       dept_cs,  prog_bsse),
            ('GA-SE-4', 'Team Collaboration',       'Function effectively in diverse teams.',                    dept_cs,  prog_bsse),
            ('GA-SE-5', 'Project Management',       'Demonstrate knowledge of project management.',              dept_cs,  prog_bsse),
            ('GA-SE-6', 'Ethics & Professionalism', 'Apply professional ethics in SE practice.',                 dept_cs,  prog_bsse),
            ('GA-B1',   'Business Knowledge',       'Demonstrate foundational business knowledge.',              dept_biz, prog_bba),
            ('GA-B2',   'Critical Thinking',        'Analyse business problems using quantitative methods.',     dept_biz, prog_bba),
            ('GA-B3',   'Communication',            'Communicate effectively in written and oral formats.',      dept_biz, prog_bba),
            ('GA-B4',   'Leadership',               'Demonstrate leadership and team management skills.',        dept_biz, prog_bba),
            ('GA-B5',   'Ethics & Social Resp.',    'Apply ethical standards in business decisions.',            dept_biz, prog_bba),
            ('GA-B6',   'Entrepreneurship',         'Identify entrepreneurial opportunities.',                   dept_biz, prog_bba),
            ('GA-M1',   'Strategic Management',     'Formulate competitive business strategies.',                dept_biz, prog_mba),
            ('GA-M2',   'Financial Acumen',         'Apply advanced financial analysis.',                        dept_biz, prog_mba),
            ('GA-M3',   'Global Business',          'Evaluate global business environments.',                    dept_biz, prog_mba),
            ('GA-M4',   'Leadership & Change',      'Lead organisational change initiatives.',                   dept_biz, prog_mba),
        ]
        for ga_id, name, desc, dept, prog in ga_data:
            ga = GraduateAttribute.objects.create(
                ga_id=ga_id, name=name, description=desc,
                department=dept, program=prog
            )
            all_gas[ga_id] = ga
        self.stdout.write('  ✓ Graduate Attributes')

        # ── Program Objectives ────────────────────────────────────────────────
        po_data = {
            prog_bscs: [
                ('PO1', 'Apply knowledge of mathematics and computing to solve complex problems.', ['GA-1', 'GA-2']),
                ('PO2', 'Design and implement software systems meeting specified requirements.',    ['GA-3', 'GA-5']),
                ('PO3', 'Conduct investigation of complex problems using research-based methods.', ['GA-4', 'GA-2']),
                ('PO4', 'Apply professional ethics and responsibilities in computing practice.',   ['GA-6']),
            ],
            prog_bsse: [
                ('PO1', 'Apply SE principles to design, develop, and maintain software systems.', ['GA-SE-1', 'GA-SE-3']),
                ('PO2', 'Analyse user requirements and translate them into reliable solutions.',   ['GA-SE-2', 'GA-SE-3']),
                ('PO3', 'Work effectively in teams using industry-standard tools.',               ['GA-SE-4', 'GA-SE-5']),
                ('PO4', 'Demonstrate ethical conduct in software engineering.',                   ['GA-SE-6']),
            ],
            prog_bba: [
                ('PO1', 'Demonstrate comprehensive knowledge across core business functions.',     ['GA-B1', 'GA-B2']),
                ('PO2', 'Communicate business insights clearly to diverse audiences.',            ['GA-B3']),
                ('PO3', 'Lead and manage teams with sound judgment.',                            ['GA-B4', 'GA-B5']),
                ('PO4', 'Identify and develop entrepreneurial ventures.',                         ['GA-B6', 'GA-B2']),
            ],
            prog_mba: [
                ('PO1', 'Formulate competitive strategies creating sustainable value.',           ['GA-M1', 'GA-M2']),
                ('PO2', 'Evaluate global market opportunities and mitigate risks.',              ['GA-M3', 'GA-M1']),
                ('PO3', 'Lead transformational change with stakeholder alignment.',              ['GA-M4', 'GA-M1']),
                ('PO4', 'Apply advanced financial models for investment decisions.',             ['GA-M2']),
            ],
        }
        for program, pos in po_data.items():
            for code, desc, ga_ids in pos:
                po = ProgramObjective.objects.create(
                    program=program, code=code, description=desc
                )
                for ga_id in ga_ids:
                    if ga_id in all_gas:
                        POGAMapping.objects.create(
                            program_objective=po,
                            graduate_attribute=all_gas[ga_id]
                        )
        self.stdout.write('  ✓ Program Objectives + PO-GA Mappings')

        # ── QA Courses ────────────────────────────────────────────────────────
        course_data = [
            ('C1',  'CMC111', 'Programming Fundamentals',               'core',     prog_bscs, dept_cs,  ['GA-1','GA-2']),
            ('C2',  'CMC211', 'Object Oriented Programming',            'core',     prog_bscs, dept_cs,  ['GA-1','GA-3']),
            ('C3',  'CMC311', 'Data Structures and Algorithms',         'core',     prog_bscs, dept_cs,  ['GA-2','GA-3','GA-4']),
            ('C4',  'CMC321', 'Database Systems',                       'core',     prog_bscs, dept_cs,  ['GA-3','GA-5']),
            ('C5',  'CMC411', 'Artificial Intelligence',                'core',     prog_bscs, dept_cs,  ['GA-4','GA-5']),
            ('C6',  'CMC412', 'Machine Learning',                       'elective', prog_bscs, dept_cs,  ['GA-4','GA-5']),
            ('C7',  'CMC322', 'Computer Networks',                      'core',     prog_bscs, dept_cs,  ['GA-1','GA-5']),
            ('C8',  'CMC421', 'Final Year Project',                     'core',     prog_bscs, dept_cs,  ['GA-3','GA-4','GA-6']),
            ('SE1', 'SWE111', 'Introduction to Software Engineering',   'core',     prog_bsse, dept_cs,  ['GA-SE-1','GA-SE-2']),
            ('SE2', 'SWE211', 'Software Requirements Engineering',      'core',     prog_bsse, dept_cs,  ['GA-SE-2','GA-SE-3']),
            ('SE3', 'SWE221', 'Software Design and Architecture',       'core',     prog_bsse, dept_cs,  ['GA-SE-3']),
            ('SE4', 'SWE311', 'Software Testing and Quality',           'core',     prog_bsse, dept_cs,  ['GA-SE-1','GA-SE-3']),
            ('SE5', 'SWE321', 'Software Project Management',            'core',     prog_bsse, dept_cs,  ['GA-SE-4','GA-SE-5']),
            ('SE6', 'SWE411', 'Agile and DevOps Practices',             'elective', prog_bsse, dept_cs,  ['GA-SE-4','GA-SE-5']),
            ('SE7', 'SWE421', 'Capstone Project',                       'core',     prog_bsse, dept_cs,  ['GA-SE-3','GA-SE-4','GA-SE-6']),
            ('B1',  'BBA101', 'Principles of Management',               'core',     prog_bba,  dept_biz, ['GA-B1','GA-B4']),
            ('B2',  'BBA201', 'Financial Accounting',                   'core',     prog_bba,  dept_biz, ['GA-B1','GA-B2']),
            ('B3',  'BBA211', 'Marketing Management',                   'core',     prog_bba,  dept_biz, ['GA-B1','GA-B3']),
            ('B4',  'BBA301', 'Business Ethics and Law',                'core',     prog_bba,  dept_biz, ['GA-B5']),
            ('B5',  'BBA311', 'Entrepreneurship',                       'elective', prog_bba,  dept_biz, ['GA-B6','GA-B2']),
            ('B6',  'BBA401', 'Strategic Management',                   'core',     prog_bba,  dept_biz, ['GA-B2','GA-B4']),
            ('M1',  'MBA501', 'Corporate Strategy',                     'core',     prog_mba,  dept_biz, ['GA-M1','GA-M2']),
            ('M2',  'MBA511', 'International Business',                 'core',     prog_mba,  dept_biz, ['GA-M3']),
            ('M3',  'MBA521', 'Leadership and Organisational Behaviour','core',     prog_mba,  dept_biz, ['GA-M4','GA-M1']),
            ('M4',  'MBA531', 'Advanced Financial Management',          'core',     prog_mba,  dept_biz, ['GA-M2']),
            ('M5',  'MBA601', 'MBA Thesis',                             'core',     prog_mba,  dept_biz, ['GA-M1','GA-M3','GA-M4']),
        ]
        for slug, code, title, ctype, program, dept, ga_ids in course_data:
            course = Course.objects.create(
                slug=slug, code=code, title=title, type=ctype,
                program=program, department=dept, credit_hours=3
            )
            course.mapped_gas.set([all_gas[g] for g in ga_ids if g in all_gas])
        self.stdout.write('  ✓ QA Courses')

        # ── Users ─────────────────────────────────────────────────────────────
        qa_cs = User.objects.create(
            username='qa_computing', email='qa.computing@iqra.edu.pk',
            first_name='Sara', last_name='Khan',
            role='qa', password=make_password('qapass123'), is_active=True
        )
        QAProfile.objects.create(user=qa_cs, department=dept_cs, employee_id='QA-CS-001')

        qa_biz = User.objects.create(
            username='qa_business', email='qa.business@iqra.edu.pk',
            first_name='Nadia', last_name='Ahmed',
            role='qa', password=make_password('qapass123'), is_active=True
        )
        QAProfile.objects.create(user=qa_biz, department=dept_biz, employee_id='QA-BIZ-001')

        instructors = []
        for username, first, last, email, dept, emp_id, designation in [
            ('dr_ali',    'Dr. Ali',    'Hassan', 'ali.hassan@iqra.edu.pk',   dept_cs,  'INS-CS-001',  'Associate Professor'),
            ('dr_fatima', 'Dr. Fatima', 'Malik',  'fatima.malik@iqra.edu.pk', dept_cs,  'INS-CS-002',  'Assistant Professor'),
            ('dr_usman',  'Dr. Usman',  'Sheikh', 'usman.sheikh@iqra.edu.pk', dept_biz, 'INS-BIZ-001', 'Senior Lecturer'),
        ]:
            u = User.objects.create(
                username=username, email=email,
                first_name=first, last_name=last,
                role='instructor', password=make_password('instpass123'), is_active=True
            )
            p = InstructorProfile.objects.create(
                user=u, department=dept,
                employee_id=emp_id, designation=designation
            )
            instructors.append((username, p))

        for username, first, last, email, prog, roll, batch in [
            ('ahmed_cs',  'Ahmed', 'Raza',     'ahmed.raza@student.iqra.edu.pk',    prog_bscs, 'FA22-BSCS-0012', 2022),
            ('zara_cs',   'Zara',  'Siddiqui', 'zara.siddiqui@student.iqra.edu.pk', prog_bscs, 'FA22-BSCS-0045', 2022),
            ('hamza_se',  'Hamza', 'Tariq',    'hamza.tariq@student.iqra.edu.pk',   prog_bsse, 'FA22-BSSE-0001', 2022),
            ('aisha_bba', 'Aisha', 'Nawaz',    'aisha.nawaz@student.iqra.edu.pk',   prog_bba,  'FA22-BBA-0001',  2022),
        ]:
            u = User.objects.create(
                username=username, email=email,
                first_name=first, last_name=last,
                role='student', password=make_password('stupass123'), is_active=True
            )
            Student.objects.create(user=u, program=prog, roll_number=roll, batch_year=batch)

        self.stdout.write('  ✓ Users')

        # ── Instructor Demo Course ────────────────────────────────────────────
        dr_ali_profile = InstructorProfile.objects.get(user__username='dr_ali')

        course = InstructorCourse.objects.create(
            instructor=dr_ali_profile,
            frontend_id='course-demo-1',
            code='CMC371',
            title='Software Engineering',
            department=dept_cs,
            program=prog_bscs,
            credit_hours=3,
            clo_count=4,
            selected_grading_system='ready1',
        )

        # GradeScale (custom example even though ready1 is selected)
        for order, (grade, pct, pts) in enumerate([
            ('A',  90.0, 4.0), ('A-', 85.0, 3.7), ('B+', 80.0, 3.3),
            ('B',  75.0, 3.0), ('B-', 70.0, 2.7), ('C+', 65.0, 2.3),
            ('C',  60.0, 2.0), ('C-', 55.0, 1.7), ('D',  50.0, 1.0),
            ('F',   0.0, 0.0),
        ]):
            GradeScale.objects.create(
                course=course, grade=grade,
                min_percentage=pct, points=pts, order=order
            )

        # Categories + UnitItems
        categories_config = [
            ('Assignments',          15, 3, [(1,10,5,33.3,['CLO-1','CLO-2']),
                                              (2,10,5,33.3,['CLO-2','CLO-3']),
                                              (3,10,5,33.4,['CLO-1','CLO-3'])]),
            ('Quizzes',              10, 3, [(1,10,5,33.3,['CLO-1','CLO-2']),
                                              (2,10,5,33.3,['CLO-3','CLO-4']),
                                              (3,10,5,33.4,['CLO-1','CLO-4'])]),
            ('Class Participation',   5, 1, [(1,10,5,100,['CLO-1','CLO-2','CLO-3','CLO-4'])]),
            ('Class Project',        15, 1, [(1,30,15,100,['CLO-2','CLO-3','CLO-4'])]),
            ('Presentation',          5, 1, [(1,10,5,100,['CLO-1','CLO-2'])]),
            ('Mid Term',             20, 1, [(1,30,15,100,['CLO-1','CLO-2','CLO-3'])]),
            ('Final',                30, 1, [(1,40,20,100,['CLO-1','CLO-2','CLO-3','CLO-4'])]),
        ]

        unit_obj_map = {}   # (cat_name, unit_no) -> UnitItem
        for order, (cat_name, pct, units, unit_list) in enumerate(categories_config):
            cat = MarksCategory.objects.create(
                course=course, name=cat_name,
                percentage=pct, units=units, order=order
            )
            for unit_no, total, passing, weightage, clos in unit_list:
                u = UnitItem.objects.create(
                    category=cat, unit_no=unit_no,
                    total_marks=total, passing=passing,
                    weightage=weightage, mapped_clos=clos
                )
                unit_obj_map[(cat_name, unit_no)] = u

        self.stdout.write('  ✓ Categories + Unit Items')

        # OBE Questions
        q1 = OBEQuestion.objects.create(
            course=course, frontend_id='q-demo-1',
            unit_item=unit_obj_map[('Assignments', 1)],
            category_name='Assignments', unit_no=1,
            question_name='Q1 - Problem Identification',
            max_marks=5, mapped_clos=['CLO-1', 'CLO-2'], order=0
        )
        q2 = OBEQuestion.objects.create(
            course=course, frontend_id='q-demo-2',
            unit_item=unit_obj_map[('Assignments', 1)],
            category_name='Assignments', unit_no=1,
            question_name='Q2 - Solution Design',
            max_marks=5, mapped_clos=['CLO-3'], order=1
        )
        q3 = OBEQuestion.objects.create(
            course=course, frontend_id='q-demo-3',
            unit_item=unit_obj_map[('Quizzes', 1)],
            category_name='Quizzes', unit_no=1,
            question_name='Q1 - Concept Application',
            max_marks=10, mapped_clos=['CLO-1', 'CLO-3', 'CLO-4'], order=0
        )
        q4 = OBEQuestion.objects.create(
            course=course, frontend_id='q-demo-4',
            unit_item=unit_obj_map[('Mid Term', 1)],
            category_name='Mid Term', unit_no=1,
            question_name='Q1 - Analysis',
            max_marks=15, mapped_clos=['CLO-1', 'CLO-2'], order=0
        )
        q5 = OBEQuestion.objects.create(
            course=course, frontend_id='q-demo-5',
            unit_item=unit_obj_map[('Mid Term', 1)],
            category_name='Mid Term', unit_no=1,
            question_name='Q2 - Design',
            max_marks=15, mapped_clos=['CLO-2', 'CLO-3'], order=1
        )
        self.stdout.write('  ✓ OBE Questions')

        # Students + Marks + OBE Marks
        students_seed = [
            {
                'reg_no': 'FA22-BSCS-0012', 'name': 'Abdur Rehman Khalid',
                'marks': {
                    ('Assignments',1):8.5, ('Assignments',2):9.0, ('Assignments',3):7.5,
                    ('Quizzes',1):7.0,     ('Quizzes',2):8.5,     ('Quizzes',3):9.0,
                    ('Class Participation',1):9.0,
                    ('Class Project',1):26.5,
                    ('Presentation',1):8.0,
                    ('Mid Term',1):24.5,
                    ('Final',1):34.0,
                },
                'obe_marks': {
                    'q-demo-1': 4.5, 'q-demo-2': 4.0,
                    'q-demo-3': 8.0, 'q-demo-4': 12.5, 'q-demo-5': 12.0,
                },
            },
            {
                'reg_no': 'FA22-BSCS-0045', 'name': 'Syeda Fatima Alvi',
                'marks': {
                    ('Assignments',1):9.0, ('Assignments',2):8.0, ('Assignments',3):8.5,
                    ('Quizzes',1):8.0,     ('Quizzes',2):7.5,     ('Quizzes',3):6.5,
                    ('Class Participation',1):8.0,
                    ('Class Project',1):25.0,
                    ('Presentation',1):9.0,
                    ('Mid Term',1):22.0,
                    ('Final',1):32.5,
                },
                'obe_marks': {
                    'q-demo-1': 5.0, 'q-demo-2': 3.5,
                    'q-demo-3': 7.5, 'q-demo-4': 11.0, 'q-demo-5': 11.0,
                },
            },
            {
                'reg_no': 'FA22-BSCS-0089', 'name': 'Zayan Ahmed Khan',
                'marks': {
                    ('Assignments',1):7.5, ('Assignments',2):7.0, ('Assignments',3):8.0,
                    ('Quizzes',1):6.0,     ('Quizzes',2):5.0,     ('Quizzes',3):7.0,
                    ('Class Participation',1):7.0,
                    ('Class Project',1):22.0,
                    ('Presentation',1):7.5,
                    ('Mid Term',1):19.5,
                    ('Final',1):28.0,
                },
                'obe_marks': {
                    'q-demo-1': 3.5, 'q-demo-2': 2.5,
                    'q-demo-3': 5.0, 'q-demo-4': 9.5,  'q-demo-5': 10.0,
                },
            },
        ]

        question_map = {
            'q-demo-1': q1, 'q-demo-2': q2,
            'q-demo-3': q3, 'q-demo-4': q4, 'q-demo-5': q5,
        }

        for s_data in students_seed:
            student = CourseStudent.objects.create(
                course=course,
                reg_no=s_data['reg_no'],
                name=s_data['name']
            )
            for (cat_name, unit_no), score in s_data['marks'].items():
                unit_obj = unit_obj_map.get((cat_name, unit_no))
                if unit_obj:
                    StudentMark.objects.create(
                        student=student, unit_item=unit_obj, score=score
                    )
            for q_id, score in s_data['obe_marks'].items():
                q_obj = question_map.get(q_id)
                if q_obj:
                    OBEStudentMark.objects.create(
                        student=student, question=q_obj, score=score
                    )

        self.stdout.write('  ✓ Students + Marks + OBE Marks')

        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS('\n✅  Seed complete!'))
        self.stdout.write(f'   Departments      : {Department.objects.count()}')
        self.stdout.write(f'   Programs         : {Program.objects.count()}')
        self.stdout.write(f'   GAs              : {GraduateAttribute.objects.count()}')
        self.stdout.write(f'   QA Courses       : {Course.objects.count()}')
        self.stdout.write(f'   Instructor Course : {InstructorCourse.objects.count()}')
        self.stdout.write(f'   Grade Scale Rows : {GradeScale.objects.count()}')
        self.stdout.write(f'   Categories       : {MarksCategory.objects.count()}')
        self.stdout.write(f'   Unit Items       : {UnitItem.objects.count()}')
        self.stdout.write(f'   OBE Questions    : {OBEQuestion.objects.count()}')
        self.stdout.write(f'   Students         : {CourseStudent.objects.count()}')
        self.stdout.write(f'   Student Marks    : {StudentMark.objects.count()}')
        self.stdout.write(f'   OBE Marks        : {OBEStudentMark.objects.count()}')
        self.stdout.write(f'   Users            : {User.objects.count()}')
        self.stdout.write('\n  Credentials:')
        self.stdout.write('   qa_computing / qapass123   (QA - Computing)')
        self.stdout.write('   qa_business  / qapass123   (QA - Business)')
        self.stdout.write('   dr_ali       / instpass123 (Instructor)')
        self.stdout.write('   ahmed_cs     / stupass123  (Student)')
