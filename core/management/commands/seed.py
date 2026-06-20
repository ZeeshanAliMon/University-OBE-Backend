from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from core.models import (
    User, Department, Program, ProgramObjective, POGAMapping,
    GraduateAttribute, QAProfile, InstructorProfile, Student,
    Course, InstructorCourse, GradeScale, MarksCategory, UnitItem,
    OBEQuestion, CourseStudent, StudentMark, OBEStudentMark,
)


class Command(BaseCommand):
    help = 'Seed the database with real Iqra University OBE data'

    def handle(self, *args, **kwargs):
        self.stdout.write('🌱  Seeding database ...')

        # ── Clean slate ───────────────────────────────────────────────────────
        for model in [
            OBEStudentMark, StudentMark, CourseStudent, OBEQuestion,
            UnitItem, MarksCategory, GradeScale, InstructorCourse,
            POGAMapping, ProgramObjective, Course, GraduateAttribute,
            Student, InstructorProfile, QAProfile, Program, Department,
        ]:
            model.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        self.stdout.write('  ✓ Cleared old data')

        # ── Departments ───────────────────────────────────────────────────────
        dept_cs = Department.objects.create(
            slug    = 'computing',
            name    = 'Department of Computing and Technology',
            vision  = (
                'To be a globally recognized department, acknowledged for excellence '
                'in computing education, research, and innovation, producing graduates '
                'who are ethical, creative, and technically proficient.'
            ),
            mission = (
                'To provide high-quality computing education through outcome-based '
                'learning, equipping students with strong theoretical foundations, '
                'practical skills, and the ability to adapt to the rapidly evolving '
                'technological landscape.'
            ),
        )
        dept_biz = Department.objects.create(
            slug    = 'business',
            name    = 'Department of Business Administration',
            vision  = (
                'To be a leading business school that develops ethical, innovative, '
                'and globally competent business leaders.'
            ),
            mission = (
                'To deliver rigorous, practice-oriented business education that '
                'develops analytical thinking, leadership capabilities, and '
                'entrepreneurial mindset in graduates.'
            ),
        )
        self.stdout.write('  ✓ Departments')

        # ── Programs ──────────────────────────────────────────────────────────
        prog_bscs = Program.objects.create(
            slug       = 'bscs',
            name       = 'Bachelor of Science in Computer Science',
            code       = 'BSCS',
            department = dept_cs,
            vision     = (
                'To produce computer science graduates who are innovative, '
                'ethical, and capable of solving complex real-world problems '
                'through computational thinking and technical excellence.'
            ),
            mission    = (
                'To provide a rigorous computer science curriculum that combines '
                'strong theoretical foundations with practical skills, fostering '
                'research aptitude, professional competence, and lifelong learning.'
            ),
        )
        prog_bsse = Program.objects.create(
            slug       = 'bsse',
            name       = 'Bachelor of Science in Software Engineering',
            code       = 'BSSE',
            department = dept_cs,
            vision     = (
                'To develop software engineers who deliver quality software '
                'solutions and lead engineering teams effectively.'
            ),
            mission    = (
                'To instill software engineering principles, project management '
                'skills, and professional ethics in graduates through hands-on '
                'project-based learning.'
            ),
        )
        prog_bba = Program.objects.create(
            slug       = 'bba',
            name       = 'Bachelor of Business Administration',
            code       = 'BBA',
            department = dept_biz,
            vision     = (
                'To cultivate business leaders who drive organizational success '
                'with integrity, innovation, and social responsibility.'
            ),
            mission    = (
                'To deliver a comprehensive business curriculum that integrates '
                'theory, practice, and ethical leadership to prepare graduates '
                'for dynamic business environments.'
            ),
        )
        prog_mba = Program.objects.create(
            slug       = 'mba',
            name       = 'Master of Business Administration',
            code       = 'MBA',
            department = dept_biz,
            vision     = (
                'To produce strategic thinkers and transformational leaders '
                'ready for global business challenges.'
            ),
            mission    = (
                'To develop advanced managerial and leadership capabilities '
                'through rigorous academic and experiential learning.'
            ),
        )
        self.stdout.write('  ✓ Programs')

        # ── Graduate Attributes ───────────────────────────────────────────────
        # Real Iqra University GAs matching the frontend fallback exactly
        all_gas = {}

        cs_gas = [
            ('GA-1',  'Academic Education and Knowledge',
             'An ability to apply knowledge of computing, mathematics, science and engineering.'),
            ('GA-2',  'Problem Analysis',
             'An ability to identify, formulate, research literature, and analyse complex computing problems.'),
            ('GA-3',  'Design and Development of Solutions',
             'An ability to design solutions for complex computing problems and design systems, components, or processes.'),
            ('GA-4',  'Modern Tool Usage',
             'An ability to create, select, and apply appropriate techniques, resources, and modern computing tools.'),
            ('GA-5',  'Individual and Team Work',
             'An ability to function effectively as an individual and as a member or leader in diverse teams.'),
            ('GA-6',  'Communication',
             'An ability to communicate effectively on complex computing activities with the computing community and with society at large.'),
            ('GA-7',  'Ethics',
             'An ability to apply ethical principles and commit to professional ethics and responsibilities.'),
            ('GA-8',  'Project Management',
             'An ability to demonstrate knowledge and understanding of computing and management principles.'),
            ('GA-9',  'Life Long Learning',
             'An ability to recognize the need for, and have the preparation and ability to engage in independent and life-long learning.'),
            ('GA-10', 'Environment and Society',
             'An ability to understand the impact of computing solutions in societal and environmental contexts.'),
        ]

        biz_gas = [
            ('GA-B1', 'Business Knowledge',
             'Demonstrate and apply knowledge of business disciplines including management, marketing, finance and accounting.'),
            ('GA-B2', 'Critical Thinking and Problem Solving',
             'Analyse complex business problems using both quantitative and qualitative methods to recommend solutions.'),
            ('GA-B3', 'Communication',
             'Communicate effectively in written, oral, and digital formats across diverse business contexts.'),
            ('GA-B4', 'Leadership and Teamwork',
             'Demonstrate leadership skills, collaborate effectively, and manage teams toward achieving organizational goals.'),
            ('GA-B5', 'Ethics and Social Responsibility',
             'Apply ethical standards and social responsibility principles in business decision-making.'),
            ('GA-B6', 'Entrepreneurship and Innovation',
             'Identify entrepreneurial opportunities and develop viable, innovative business ideas and plans.'),
            ('GA-B7', 'Global Business Awareness',
             'Evaluate global business environments and assess international market dynamics and cultural differences.'),
            ('GA-B8', 'Technology and Digital Literacy',
             'Apply technology and digital tools effectively in business operations, analysis, and decision-making.'),
        ]

        for ga_id, name, desc in cs_gas:
            ga = GraduateAttribute.objects.create(
                ga_id=ga_id, name=name, description=desc, department=dept_cs
            )
            all_gas[ga_id] = ga

        for ga_id, name, desc in biz_gas:
            ga = GraduateAttribute.objects.create(
                ga_id=ga_id, name=name, description=desc, department=dept_biz
            )
            all_gas[ga_id] = ga

        self.stdout.write('  ✓ Graduate Attributes (10 Computing + 8 Business)')

        # ── Program Objectives ────────────────────────────────────────────────
        po_data = {
            prog_bscs: [
                ('PO1', 'Apply knowledge of mathematics, science and computing fundamentals to solve complex problems.',
                 ['GA-1', 'GA-2']),
                ('PO2', 'Design and implement software and computing systems that meet specified requirements with appropriate constraints.',
                 ['GA-3', 'GA-4']),
                ('PO3', 'Function effectively as an individual and in teams while communicating clearly and professionally.',
                 ['GA-5', 'GA-6']),
                ('PO4', 'Apply professional ethics and demonstrate awareness of societal, environmental and project management concerns.',
                 ['GA-7', 'GA-8', 'GA-9', 'GA-10']),
            ],
            prog_bsse: [
                ('PO1', 'Apply software engineering principles to design, develop, test and maintain reliable software systems.',
                 ['GA-1', 'GA-3']),
                ('PO2', 'Analyse user and stakeholder requirements and translate them into well-specified software solutions.',
                 ['GA-2', 'GA-3']),
                ('PO3', 'Work effectively in software development teams using modern tools and agile practices.',
                 ['GA-4', 'GA-5']),
                ('PO4', 'Demonstrate professional ethics, project management skills, and commitment to lifelong learning.',
                 ['GA-7', 'GA-8', 'GA-9']),
            ],
            prog_bba: [
                ('PO1', 'Demonstrate comprehensive knowledge across core business disciplines.',
                 ['GA-B1', 'GA-B2']),
                ('PO2', 'Communicate business insights clearly and persuasively to diverse audiences.',
                 ['GA-B3']),
                ('PO3', 'Lead and manage teams with emotional intelligence, ethics and sound business judgment.',
                 ['GA-B4', 'GA-B5']),
                ('PO4', 'Identify entrepreneurial opportunities and evaluate global business and technology trends.',
                 ['GA-B6', 'GA-B7', 'GA-B8']),
            ],
            prog_mba: [
                ('PO1', 'Formulate and implement competitive business strategies that create sustainable organisational value.',
                 ['GA-B1', 'GA-B2']),
                ('PO2', 'Lead transformational change initiatives with effective stakeholder management.',
                 ['GA-B4', 'GA-B5']),
                ('PO3', 'Evaluate global market opportunities and mitigate international business risks.',
                 ['GA-B7']),
                ('PO4', 'Apply advanced financial models and digital tools to support strategic decisions.',
                 ['GA-B2', 'GA-B8']),
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

        # ── QA Courses — Computing (matching frontend fallback exactly) ────────
        cs_courses = [
            # Core BSCS courses
            ('C1',  'CMC111', 'Programming Fundamentals',                      'core',     prog_bscs, ['GA-1','GA-2']),
            ('C2',  'CMC112', 'Digital Logic Design',                          'core',     prog_bscs, ['GA-1','GA-3']),
            ('C3',  'CMC211', 'Object Oriented Programming',                   'core',     prog_bscs, ['GA-1','GA-3']),
            ('C4',  'CMC212', 'Computer Organization and Assembly Language',   'core',     prog_bscs, ['GA-1','GA-4']),
            ('C5',  'CMC213', 'Discrete Structures',                           'core',     prog_bscs, ['GA-1','GA-2']),
            ('C6',  'CMC221', 'Data Structures',                               'core',     prog_bscs, ['GA-2','GA-3']),
            ('C7',  'CMC222', 'Database Systems',                              'core',     prog_bscs, ['GA-3','GA-4']),
            ('C8',  'CMC311', 'Design and Analysis of Algorithms',             'core',     prog_bscs, ['GA-2','GA-3']),
            ('C9',  'CMC312', 'Operating Systems',                             'core',     prog_bscs, ['GA-1','GA-3']),
            ('C10', 'CMC313', 'Software Engineering',                          'core',     prog_bscs, ['GA-3','GA-8']),
            ('C11', 'CMC321', 'Computer Networks',                             'core',     prog_bscs, ['GA-1','GA-4']),
            ('C12', 'CMC322', 'Theory of Automata',                            'core',     prog_bscs, ['GA-1','GA-2']),
            ('C13', 'CMC411', 'Artificial Intelligence',                       'core',     prog_bscs, ['GA-3','GA-4']),
            ('C14', 'CMC412', 'Compiler Construction',                         'core',     prog_bscs, ['GA-1','GA-3']),
            ('C15', 'CMC413', 'Information Security',                          'core',     prog_bscs, ['GA-3','GA-7']),
            ('C16', 'CMC421', 'Final Year Project I',                          'core',     prog_bscs, ['GA-3','GA-5','GA-8']),
            ('C17', 'CMC422', 'Final Year Project II',                         'core',     prog_bscs, ['GA-3','GA-5','GA-6','GA-8']),
            ('C18', 'CMC423', 'Professional Practices',                        'core',     prog_bscs, ['GA-6','GA-7','GA-9']),
            # Electives
            ('C19', 'CME411', 'Machine Learning',                              'elective', prog_bscs, ['GA-3','GA-4']),
            ('C20', 'CME412', 'Deep Learning',                                 'elective', prog_bscs, ['GA-3','GA-4']),
            ('C21', 'CME413', 'Computer Vision',                               'elective', prog_bscs, ['GA-3','GA-4']),
            ('C22', 'CME421', 'Cloud Computing',                               'elective', prog_bscs, ['GA-4','GA-10']),
            ('C23', 'CME422', 'Mobile Application Development',                'elective', prog_bscs, ['GA-3','GA-4']),
            ('C24', 'CME423', 'Web Engineering',                               'elective', prog_bscs, ['GA-3','GA-4']),
            ('C25', 'CME431', 'Natural Language Processing',                   'elective', prog_bscs, ['GA-3','GA-4']),
            ('C26', 'CME432', 'Big Data Analytics',                            'elective', prog_bscs, ['GA-3','GA-4']),
            ('C27', 'CME433', 'Internet of Things',                            'elective', prog_bscs, ['GA-4','GA-10']),
            # Supporting
            ('C28', 'MTC111', 'Calculus and Analytical Geometry',              'core',     prog_bscs, ['GA-1']),
            ('C29', 'MTC211', 'Linear Algebra',                                'core',     prog_bscs, ['GA-1']),
            ('C30', 'MTC221', 'Probability and Statistics',                    'core',     prog_bscs, ['GA-1','GA-2']),
            ('C31', 'HMC111', 'Communication Skills',                          'core',     prog_bscs, ['GA-6']),
            ('C32', 'HMC211', 'Technical and Business Writing',                'core',     prog_bscs, ['GA-6']),
            ('C33', 'HMC311', 'Engineering Economics',                         'core',     prog_bscs, ['GA-8','GA-10']),
            ('C34', 'SCC111', 'Islamic Studies / Ethics',                      'core',     prog_bscs, ['GA-7']),
            ('C35', 'SCC211', 'Pakistan Studies',                              'core',     prog_bscs, ['GA-10']),
            ('C36', 'SCC311', 'Entrepreneurship',                              'core',     prog_bscs, ['GA-8','GA-9']),
        ]

        # Business courses
        biz_courses = [
            ('CB1',  'BBA101', 'Introduction to Business',                      'core',     prog_bba, ['GA-B1']),
            ('CB2',  'BBA102', 'Principles of Management',                      'core',     prog_bba, ['GA-B1','GA-B4']),
            ('CB3',  'BBA201', 'Financial Accounting',                          'core',     prog_bba, ['GA-B1','GA-B2']),
            ('CB4',  'BBA202', 'Micro Economics',                               'core',     prog_bba, ['GA-B1','GA-B2']),
            ('CB5',  'BBA211', 'Marketing Management',                          'core',     prog_bba, ['GA-B1','GA-B3']),
            ('CB6',  'BBA212', 'Organizational Behavior',                       'core',     prog_bba, ['GA-B4','GA-B5']),
            ('CB7',  'BBA301', 'Business Finance',                              'core',     prog_bba, ['GA-B1','GA-B2']),
            ('CB8',  'BBA302', 'Human Resource Management',                     'core',     prog_bba, ['GA-B4']),
            ('CB9',  'BBA311', 'Business Ethics and Law',                       'core',     prog_bba, ['GA-B5']),
            ('CB10', 'BBA312', 'Supply Chain Management',                       'core',     prog_bba, ['GA-B1','GA-B8']),
            ('CB11', 'BBA401', 'Strategic Management',                          'core',     prog_bba, ['GA-B2','GA-B4']),
            ('CB12', 'BBA402', 'Entrepreneurship and Innovation',               'elective', prog_bba, ['GA-B6','GA-B7']),
        ]

        for slug, code, title, ctype, program, ga_ids in cs_courses + biz_courses:
            course = Course.objects.create(
                slug=slug, code=code, title=title, type=ctype,
                program=program, department=program.department,
                credit_hours=3
            )
            course.mapped_gas.set([all_gas[g] for g in ga_ids if g in all_gas])

        self.stdout.write('  ✓ Courses (36 Computing + 12 Business)')

        # ── Users ─────────────────────────────────────────────────────────────
        # QA Officers
        qa_cs = User.objects.create(
            username='qa_computing', email='qa.computing@iqra.edu.pk',
            first_name='Sara', last_name='Khan',
            role='qa', password=make_password('qapass123'), is_active=True
        )
        QAProfile.objects.create(
            user=qa_cs, department=dept_cs, employee_id='QA-CS-001'
        )

        qa_biz = User.objects.create(
            username='qa_business', email='qa.business@iqra.edu.pk',
            first_name='Nadia', last_name='Ahmed',
            role='qa', password=make_password('qapass123'), is_active=True
        )
        QAProfile.objects.create(
            user=qa_biz, department=dept_biz, employee_id='QA-BIZ-001'
        )

        # Instructors
        instructor_data = [
            ('dr_ali',    'Ali',    'Hassan', 'ali.hassan@iqra.edu.pk',    dept_cs,  'INS-CS-001', 'Associate Professor'),
            ('dr_fatima', 'Fatima', 'Malik',  'fatima.malik@iqra.edu.pk',  dept_cs,  'INS-CS-002', 'Assistant Professor'),
            ('dr_usman',  'Usman',  'Sheikh', 'usman.sheikh@iqra.edu.pk',  dept_biz, 'INS-BIZ-001','Senior Lecturer'),
        ]
        instructor_profiles = {}
        for username, first, last, email, dept, emp_id, designation in instructor_data:
            u = User.objects.create(
                username=username, email=email,
                first_name=first, last_name=last,
                role='instructor', password=make_password('instpass123'), is_active=True
            )
            p = InstructorProfile.objects.create(
                user=u, department=dept,
                employee_id=emp_id, designation=designation
            )
            instructor_profiles[username] = p

        # Students
        student_data = [
            ('ahmed_cs',  'Ahmed', 'Raza',     'ahmed.raza@student.iqra.edu.pk',    prog_bscs, 'FA22-BSCS-0012', 2022),
            ('zara_cs',   'Zara',  'Siddiqui', 'zara.siddiqui@student.iqra.edu.pk', prog_bscs, 'FA22-BSCS-0045', 2022),
            ('hamza_se',  'Hamza', 'Tariq',    'hamza.tariq@student.iqra.edu.pk',   prog_bsse, 'FA22-BSSE-0001', 2022),
            ('aisha_bba', 'Aisha', 'Nawaz',    'aisha.nawaz@student.iqra.edu.pk',   prog_bba,  'FA22-BBA-0001',  2022),
        ]
        for username, first, last, email, prog, roll, batch in student_data:
            u = User.objects.create(
                username=username, email=email,
                first_name=first, last_name=last,
                role='student', password=make_password('stupass123'), is_active=True
            )
            Student.objects.create(
                user=u, program=prog, roll_number=roll, batch_year=batch
            )

        self.stdout.write('  ✓ Users (2 QA, 3 Instructors, 4 Students)')

        # ── Demo Instructor Course ────────────────────────────────────────────
        dr_ali = instructor_profiles['dr_ali']

        ic = InstructorCourse.objects.create(
            instructor=dr_ali,
            frontend_id='course-demo-1',
            code='CMC310',
            title='Software Engineering',
            department=dept_cs,
            program=prog_bscs,
            credit_hours=3,
            clo_count=4,
            selected_grading_system='ready1',
        )

        # Standard absolute grading scale
        grade_scale = [
            ('A',  90.0, 4.0, 0), ('A-', 85.0, 3.7, 1), ('B+', 80.0, 3.3, 2),
            ('B',  75.0, 3.0, 3), ('B-', 70.0, 2.7, 4), ('C+', 65.0, 2.3, 5),
            ('C',  60.0, 2.0, 6), ('C-', 55.0, 1.7, 7), ('D',  50.0, 1.0, 8),
            ('F',   0.0, 0.0, 9),
        ]
        for grade, pct, pts, order in grade_scale:
            GradeScale.objects.create(
                course=ic, grade=grade,
                min_percentage=pct, points=pts, order=order
            )

        # Categories + Units
        categories_def = [
            ('Assignments',         15, 3,  [(1,10,5,33.3,['CLO-1','CLO-2']),
                                              (2,10,5,33.3,['CLO-2','CLO-3']),
                                              (3,10,5,33.4,['CLO-1','CLO-3'])]),
            ('Quizzes',             10, 3,  [(1,10,5,33.3,['CLO-1','CLO-2']),
                                              (2,10,5,33.3,['CLO-3','CLO-4']),
                                              (3,10,5,33.4,['CLO-1','CLO-4'])]),
            ('Class Participation',  5, 1,  [(1,10,5,100,['CLO-1','CLO-2','CLO-3','CLO-4'])]),
            ('Class Project',       15, 1,  [(1,30,15,100,['CLO-2','CLO-3','CLO-4'])]),
            ('Presentation',         5, 1,  [(1,10,5,100,['CLO-1','CLO-2'])]),
            ('Mid Term',            20, 1,  [(1,30,15,100,['CLO-1','CLO-2','CLO-3'])]),
            ('Final',               30, 1,  [(1,40,20,100,['CLO-1','CLO-2','CLO-3','CLO-4'])]),
        ]

        unit_map = {}   # (cat_name, unit_no) -> UnitItem
        for order, (cat_name, pct, units, unit_list) in enumerate(categories_def):
            cat = MarksCategory.objects.create(
                course=ic, name=cat_name,
                percentage=pct, units=units, order=order
            )
            for unit_no, total, passing, weightage, clos in unit_list:
                u = UnitItem.objects.create(
                    category=cat, unit_no=unit_no,
                    total_marks=total, passing=passing,
                    weightage=weightage, mapped_clos=clos
                )
                unit_map[(cat_name, unit_no)] = u

        # OBE Questions
        questions_def = [
            ('q-demo-1', 'Assignments', 1, 'Q1 - Problem Identification',    5,  ['CLO-1','CLO-2'], 0),
            ('q-demo-2', 'Assignments', 1, 'Q2 - Solution Design',           5,  ['CLO-3'],         1),
            ('q-demo-3', 'Quizzes',     1, 'Q1 - Concept Application',       10, ['CLO-1','CLO-3','CLO-4'], 0),
            ('q-demo-4', 'Mid Term',    1, 'Q1 - Analysis',                  15, ['CLO-1','CLO-2'], 0),
            ('q-demo-5', 'Mid Term',    1, 'Q2 - System Design',             15, ['CLO-2','CLO-3'], 1),
        ]
        q_map = {}
        for fid, cat_name, unit_no, qname, max_marks, clos, order in questions_def:
            q = OBEQuestion.objects.create(
                course=ic, frontend_id=fid,
                unit_item=unit_map.get((cat_name, unit_no)),
                category_name=cat_name, unit_no=unit_no,
                question_name=qname, max_marks=max_marks,
                mapped_clos=clos, order=order
            )
            q_map[fid] = q

        # Students + marks
        students_def = [
            {
                'reg_no': 'FA22-BSCS-0012', 'name': 'Abdur Rehman Khalid',
                'marks': {
                    ('Assignments',1):8.5, ('Assignments',2):9.0, ('Assignments',3):7.5,
                    ('Quizzes',1):7.0,     ('Quizzes',2):8.5,     ('Quizzes',3):9.0,
                    ('Class Participation',1):9.0, ('Class Project',1):26.5,
                    ('Presentation',1):8.0, ('Mid Term',1):24.5, ('Final',1):34.0,
                },
                'obe': {'q-demo-1':4.5,'q-demo-2':4.0,'q-demo-3':8.0,'q-demo-4':12.5,'q-demo-5':12.0},
            },
            {
                'reg_no': 'FA22-BSCS-0045', 'name': 'Syeda Fatima Alvi',
                'marks': {
                    ('Assignments',1):9.0, ('Assignments',2):8.0, ('Assignments',3):8.5,
                    ('Quizzes',1):8.0,     ('Quizzes',2):7.5,     ('Quizzes',3):6.5,
                    ('Class Participation',1):8.0, ('Class Project',1):25.0,
                    ('Presentation',1):9.0, ('Mid Term',1):22.0, ('Final',1):32.5,
                },
                'obe': {'q-demo-1':5.0,'q-demo-2':3.5,'q-demo-3':7.5,'q-demo-4':11.0,'q-demo-5':11.0},
            },
            {
                'reg_no': 'FA22-BSCS-0089', 'name': 'Zayan Ahmed Khan',
                'marks': {
                    ('Assignments',1):7.5, ('Assignments',2):7.0, ('Assignments',3):8.0,
                    ('Quizzes',1):6.0,     ('Quizzes',2):5.0,     ('Quizzes',3):7.0,
                    ('Class Participation',1):7.0, ('Class Project',1):22.0,
                    ('Presentation',1):7.5, ('Mid Term',1):19.5, ('Final',1):28.0,
                },
                'obe': {'q-demo-1':3.5,'q-demo-2':2.5,'q-demo-3':5.0,'q-demo-4':9.5,'q-demo-5':10.0},
            },
        ]

        for s_data in students_def:
            student = CourseStudent.objects.create(
                course=ic, reg_no=s_data['reg_no'], name=s_data['name']
            )
            for (cat_name, unit_no), score in s_data['marks'].items():
                unit_obj = unit_map.get((cat_name, unit_no))
                if unit_obj:
                    StudentMark.objects.create(
                        student=student, unit_item=unit_obj, score=score
                    )
            for q_id, score in s_data['obe'].items():
                OBEStudentMark.objects.create(
                    student=student, question=q_map[q_id], score=score
                )

        self.stdout.write('  ✓ Demo Course + Marks + OBE Marks')

        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS('\n✅  Seed complete!'))
        self.stdout.write(f'   Departments      : {Department.objects.count()}')
        self.stdout.write(f'   Programs         : {Program.objects.count()}')
        self.stdout.write(f'   Graduate Attrs   : {GraduateAttribute.objects.count()}')
        self.stdout.write(f'   Program Objs     : {ProgramObjective.objects.count()}')
        self.stdout.write(f'   PO-GA Mappings   : {POGAMapping.objects.count()}')
        self.stdout.write(f'   QA Courses       : {Course.objects.count()}')
        self.stdout.write(f'   Instructor Crss  : {InstructorCourse.objects.count()}')
        self.stdout.write(f'   Grade Scale Rows : {GradeScale.objects.count()}')
        self.stdout.write(f'   Categories       : {MarksCategory.objects.count()}')
        self.stdout.write(f'   Unit Items       : {UnitItem.objects.count()}')
        self.stdout.write(f'   OBE Questions    : {OBEQuestion.objects.count()}')
        self.stdout.write(f'   Course Students  : {CourseStudent.objects.count()}')
        self.stdout.write(f'   Student Marks    : {StudentMark.objects.count()}')
        self.stdout.write(f'   OBE Marks        : {OBEStudentMark.objects.count()}')
        self.stdout.write(f'   Users            : {User.objects.count()}')
        self.stdout.write('\n  Login credentials:')
        self.stdout.write('   qa_computing / qapass123   → QA (Computing)')
        self.stdout.write('   qa_business  / qapass123   → QA (Business)')
        self.stdout.write('   dr_ali       / instpass123 → Instructor')
        self.stdout.write('   ahmed_cs     / stupass123  → Student')
