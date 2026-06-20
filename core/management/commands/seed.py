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
            vision  = 'To be a globally recognized center of excellence in computing education and research, producing innovative and ethical computing professionals who drive technological advancement.',
            mission = 'To provide high-quality, outcome-based computing education that equips graduates with strong theoretical foundations, practical skills, and professional values to excel in a rapidly evolving technological landscape.',
        )
        dept_biz = Department.objects.create(
            slug    = 'business',
            name    = 'Department of Business Administration',
            vision  = 'To be a leading business school that develops visionary leaders and entrepreneurs who create sustainable value for organizations and society.',
            mission = 'To deliver rigorous, practice-oriented business education that develops analytical thinking, leadership capabilities, and ethical decision-making in future business professionals.',
        )
        self.stdout.write('  ✓ Departments')

        # ── Programs ──────────────────────────────────────────────────────────
        prog_bscs = Program.objects.create(
            slug       = 'bscs',
            name       = 'Bachelor of Science in Computer Science',
            code       = 'BSCS',
            department = dept_cs,
            vision     = 'To produce computer science graduates who are innovative, ethical, and capable of solving complex real-world problems through cutting-edge technology.',
            mission    = 'To provide a rigorous computer science curriculum that develops strong theoretical foundations, practical programming skills, and research aptitude in graduates.',
        )
        prog_bsse = Program.objects.create(
            slug       = 'bsse',
            name       = 'Bachelor of Science in Software Engineering',
            code       = 'BSSE',
            department = dept_cs,
            vision     = 'To develop software engineering graduates who deliver high-quality software solutions and lead engineering teams in building reliable, scalable systems.',
            mission    = 'To instill software engineering principles, project management skills, and professional ethics that enable graduates to develop robust software systems.',
        )
        prog_bsai = Program.objects.create(
            slug       = 'bsai',
            name       = 'Bachelor of Science in Artificial Intelligence',
            code       = 'BSAI',
            department = dept_cs,
            vision     = 'To produce AI specialists capable of designing and deploying intelligent systems that solve complex human problems.',
            mission    = 'To provide cutting-edge AI education combining machine learning, data science, and ethics to prepare graduates for the AI-driven future.',
        )
        prog_bba = Program.objects.create(
            slug       = 'bba',
            name       = 'Bachelor of Business Administration',
            code       = 'BBA',
            department = dept_biz,
            vision     = 'To cultivate business leaders who drive organizational success with integrity, innovation, and a global perspective.',
            mission    = 'To deliver a comprehensive business curriculum that integrates theory, practice, and ethical leadership to produce well-rounded business professionals.',
        )
        prog_mba = Program.objects.create(
            slug       = 'mba',
            name       = 'Master of Business Administration',
            code       = 'MBA',
            department = dept_biz,
            vision     = 'To produce strategic thinkers and transformational leaders ready to navigate and lead in complex global business environments.',
            mission    = 'To develop advanced managerial and leadership capabilities through rigorous academic study, case-based learning, and real-world application.',
        )
        self.stdout.write('  ✓ Programs')

        # ── Graduate Attributes — Computing (matches frontend exactly) ────────
        all_gas = {}
        cs_gas = [
            ('GA-1',  'Academic Education',
             'An ability to apply knowledge of computing, mathematics, science and engineering fundamentals appropriate to the discipline.',
             dept_cs),
            ('GA-2',  'Problem Analysis',
             'An ability to identify, formulate, research literature and analyse complex computing problems reaching substantiated conclusions using first principles of mathematics and engineering sciences.',
             dept_cs),
            ('GA-3',  'Design/Development of Solutions',
             'An ability to design solutions for complex computing problems and design system components, processes or programs that meet the specified needs with appropriate consideration for public health and safety, and cultural, societal, and environmental considerations.',
             dept_cs),
            ('GA-4',  'Investigation',
             'An ability to investigate complex computing problems in a methodical way including literature survey, design and conduct of experiments, analysis and interpretation of experimental data, and synthesis of the information to derive valid conclusions.',
             dept_cs),
            ('GA-5',  'Modern Tool Usage',
             'An ability to create, select, learn and apply appropriate techniques, resources, and modern engineering and IT tools including prediction and modelling to complex computing activities with an understanding of the limitations.',
             dept_cs),
            ('GA-6',  'The Engineer and Society',
             'An ability to apply reasoning informed by the contextual knowledge to assess societal, health, safety, legal and cultural issues and the consequent responsibilities relevant to the professional computing practice.',
             dept_cs),
            ('GA-7',  'Environment and Sustainability',
             'An ability to understand the impact of the professional computing solutions in societal and environmental contexts, and demonstrate the knowledge of, and need for sustainable development.',
             dept_cs),
            ('GA-8',  'Ethics',
             'Apply ethical principles and commit to professional ethics and responsibilities and norms of the computing practice.',
             dept_cs),
            ('GA-9',  'Individual and Team Work',
             'An ability to work effectively, as an individual or in a team, on multifaceted and /or multidisciplinary settings.',
             dept_cs),
            ('GA-10', 'Communication',
             'An ability to communicate effectively, orally as well as in writing, on complex computing activities with the computing community and with society at large, such as, being able to comprehend and write effective reports and design documentation, make effective presentations, and give and receive clear instructions.',
             dept_cs),
        ]
        for ga_id, name, desc, dept in cs_gas:
            ga = GraduateAttribute.objects.create(
                ga_id=ga_id, name=name, description=desc, department=dept
            )
            all_gas[ga_id] = ga

        # ── Graduate Attributes — Business (matches frontend exactly) ─────────
        biz_gas = [
            ('GA-B1', 'Business Knowledge',
             'An ability to apply knowledge of business administration, management principles, and quantitative methods to solve complex business problems.',
             dept_biz),
            ('GA-B2', 'Critical Thinking & Problem Analysis',
             'An ability to identify, analyse and evaluate complex business problems using analytical and quantitative tools, reaching well-reasoned conclusions.',
             dept_biz),
            ('GA-B3', 'Ethical Leadership',
             'An ability to demonstrate ethical leadership, apply professional standards, and commit to corporate social responsibility in business practice.',
             dept_biz),
            ('GA-B4', 'Communication',
             'An ability to communicate effectively in written, oral, and digital formats with diverse business audiences.',
             dept_biz),
            ('GA-B5', 'Team Collaboration',
             'An ability to work effectively as an individual and as a member or leader in diverse and multidisciplinary business teams.',
             dept_biz),
            ('GA-B6', 'Entrepreneurship & Innovation',
             'An ability to identify entrepreneurial opportunities, develop viable business plans, and demonstrate innovative thinking in business contexts.',
             dept_biz),
            ('GA-B7', 'Global Business Awareness',
             'An ability to understand and evaluate global business environments, international trade, and cross-cultural management challenges.',
             dept_biz),
            ('GA-B8', 'Life-long Learning',
             'An ability to recognize the need for, and have the capacity to engage in independent and life-long learning in the context of business and management.',
             dept_biz),
        ]
        for ga_id, name, desc, dept in biz_gas:
            ga = GraduateAttribute.objects.create(
                ga_id=ga_id, name=name, description=desc, department=dept
            )
            all_gas[ga_id] = ga

        self.stdout.write('  ✓ Graduate Attributes (10 Computing + 8 Business)')

        # ── Program Objectives ────────────────────────────────────────────────
        po_data = {
            prog_bscs: [
                ('PO1', 'Apply knowledge of mathematics, science, and computing fundamentals to solve complex computing problems.',
                 ['GA-1', 'GA-2']),
                ('PO2', 'Design and develop software systems and components that meet specified requirements.',
                 ['GA-3', 'GA-5']),
                ('PO3', 'Investigate complex computing problems using research-based methodologies and experimental techniques.',
                 ['GA-4', 'GA-2']),
                ('PO4', 'Function effectively in teams and communicate clearly in professional and societal contexts.',
                 ['GA-9', 'GA-10']),
                ('PO5', 'Apply professional ethics and demonstrate awareness of societal, legal, and environmental impacts.',
                 ['GA-6', 'GA-7', 'GA-8']),
            ],
            prog_bsse: [
                ('PO1', 'Apply software engineering principles to design, develop, test and maintain software systems.',
                 ['GA-1', 'GA-3']),
                ('PO2', 'Analyse complex software requirements and translate them into reliable, scalable solutions.',
                 ['GA-2', 'GA-3']),
                ('PO3', 'Apply modern software engineering tools, methodologies and best practices effectively.',
                 ['GA-5', 'GA-4']),
                ('PO4', 'Work effectively in teams, manage software projects, and communicate technical solutions.',
                 ['GA-9', 'GA-10']),
                ('PO5', 'Demonstrate professional ethics and responsibility in software engineering practice.',
                 ['GA-8', 'GA-6']),
            ],
            prog_bsai: [
                ('PO1', 'Apply mathematical foundations and AI principles to design intelligent systems.',
                 ['GA-1', 'GA-3']),
                ('PO2', 'Analyse data-driven problems and develop machine learning and AI solutions.',
                 ['GA-2', 'GA-4']),
                ('PO3', 'Apply modern AI frameworks and tools to build and deploy intelligent applications.',
                 ['GA-5', 'GA-3']),
                ('PO4', 'Evaluate ethical, societal and environmental implications of AI systems.',
                 ['GA-6', 'GA-7', 'GA-8']),
                ('PO5', 'Communicate AI research findings and work effectively in interdisciplinary teams.',
                 ['GA-9', 'GA-10']),
            ],
            prog_bba: [
                ('PO1', 'Apply comprehensive business knowledge across core disciplines to address complex organizational challenges.',
                 ['GA-B1', 'GA-B2']),
                ('PO2', 'Demonstrate ethical leadership and corporate social responsibility in business decision-making.',
                 ['GA-B3', 'GA-B5']),
                ('PO3', 'Communicate business insights effectively and work collaboratively in diverse teams.',
                 ['GA-B4', 'GA-B5']),
                ('PO4', 'Identify and develop entrepreneurial opportunities with a global business perspective.',
                 ['GA-B6', 'GA-B7']),
            ],
            prog_mba: [
                ('PO1', 'Formulate and implement competitive business strategies that create sustainable organizational value.',
                 ['GA-B1', 'GA-B2']),
                ('PO2', 'Lead organizational change and demonstrate transformational leadership with ethical responsibility.',
                 ['GA-B3', 'GA-B5']),
                ('PO3', 'Evaluate global business environments and develop international business strategies.',
                 ['GA-B7', 'GA-B2']),
                ('PO4', 'Apply advanced financial analysis and decision-making frameworks for strategic investment.',
                 ['GA-B1', 'GA-B2']),
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

        # ── QA Courses — Computing (real Iqra curriculum) ─────────────────────
        cs_courses = [
            # BSCS Core
            ('C1',  'CS-101',  'Introduction to Computing',                'core',     prog_bscs, 3, ['GA-1','GA-9']),
            ('C2',  'CS-201',  'Programming Fundamentals',                 'core',     prog_bscs, 3, ['GA-1','GA-2']),
            ('C3',  'CS-202',  'Object Oriented Programming',              'core',     prog_bscs, 3, ['GA-1','GA-3']),
            ('C4',  'CS-301',  'Data Structures and Algorithms',           'core',     prog_bscs, 3, ['GA-2','GA-3']),
            ('C5',  'CS-302',  'Database Systems',                         'core',     prog_bscs, 3, ['GA-3','GA-5']),
            ('C6',  'CS-303',  'Computer Networks',                        'core',     prog_bscs, 3, ['GA-1','GA-5']),
            ('C7',  'CS-304',  'Operating Systems',                        'core',     prog_bscs, 3, ['GA-1','GA-3']),
            ('C8',  'CS-305',  'Software Engineering',                     'core',     prog_bscs, 3, ['GA-3','GA-9']),
            ('C9',  'CS-306',  'Discrete Mathematics',                     'core',     prog_bscs, 3, ['GA-1','GA-2']),
            ('C10', 'CS-401',  'Artificial Intelligence',                  'core',     prog_bscs, 3, ['GA-2','GA-5']),
            ('C11', 'CS-402',  'Computer Architecture',                    'core',     prog_bscs, 3, ['GA-1','GA-3']),
            ('C12', 'CS-403',  'Web Technologies',                         'core',     prog_bscs, 3, ['GA-3','GA-5']),
            ('C13', 'CS-404',  'Information Security',                     'core',     prog_bscs, 3, ['GA-5','GA-6','GA-8']),
            ('C14', 'CS-405',  'Human Computer Interaction',               'core',     prog_bscs, 3, ['GA-3','GA-10']),
            ('C15', 'CS-406',  'Parallel and Distributed Computing',       'core',     prog_bscs, 3, ['GA-1','GA-3']),
            ('C16', 'CS-407',  'Theory of Automata',                       'core',     prog_bscs, 3, ['GA-1','GA-2']),
            ('C17', 'CS-408',  'Compiler Construction',                    'core',     prog_bscs, 3, ['GA-2','GA-3']),
            ('C18', 'CS-409',  'Final Year Project I',                     'core',     prog_bscs, 3, ['GA-3','GA-4','GA-9','GA-10']),
            ('C19', 'CS-410',  'Final Year Project II',                    'core',     prog_bscs, 3, ['GA-3','GA-4','GA-9','GA-10']),
            # BSCS Electives
            ('C20', 'CS-451',  'Machine Learning',                         'elective', prog_bscs, 3, ['GA-2','GA-5']),
            ('C21', 'CS-452',  'Deep Learning',                            'elective', prog_bscs, 3, ['GA-2','GA-5']),
            ('C22', 'CS-453',  'Cloud Computing',                          'elective', prog_bscs, 3, ['GA-3','GA-5']),
            ('C23', 'CS-454',  'Mobile Application Development',           'elective', prog_bscs, 3, ['GA-3','GA-5']),
            ('C24', 'CS-455',  'Computer Vision',                          'elective', prog_bscs, 3, ['GA-2','GA-5']),
            ('C25', 'CS-456',  'Natural Language Processing',              'elective', prog_bscs, 3, ['GA-2','GA-5']),
            ('C26', 'CS-457',  'Big Data Analytics',                       'elective', prog_bscs, 3, ['GA-4','GA-5']),
            ('C27', 'CS-458',  'Blockchain Technology',                    'elective', prog_bscs, 3, ['GA-3','GA-5']),
            ('C28', 'CS-459',  'Internet of Things',                       'elective', prog_bscs, 3, ['GA-3','GA-5']),
            ('C29', 'CS-460',  'Game Development',                         'elective', prog_bscs, 3, ['GA-3','GA-5']),
            # BSSE
            ('SE1', 'SE-301',  'Software Requirements Engineering',        'core',     prog_bsse, 3, ['GA-2','GA-3']),
            ('SE2', 'SE-302',  'Software Design and Architecture',         'core',     prog_bsse, 3, ['GA-3','GA-5']),
            ('SE3', 'SE-303',  'Software Testing and Quality Assurance',   'core',     prog_bsse, 3, ['GA-2','GA-4']),
            ('SE4', 'SE-304',  'Software Project Management',              'core',     prog_bsse, 3, ['GA-9','GA-10']),
            ('SE5', 'SE-401',  'Agile Software Development',               'core',     prog_bsse, 3, ['GA-3','GA-9']),
            ('SE6', 'SE-402',  'DevOps and Continuous Delivery',           'elective', prog_bsse, 3, ['GA-3','GA-5']),
            ('SE7', 'SE-403',  'Capstone Project I',                       'core',     prog_bsse, 3, ['GA-3','GA-9','GA-10']),
            ('SE8', 'SE-404',  'Capstone Project II',                      'core',     prog_bsse, 3, ['GA-3','GA-9','GA-10']),
            # BSAI
            ('AI1', 'AI-301',  'Machine Learning',                         'core',     prog_bsai, 3, ['GA-2','GA-5']),
            ('AI2', 'AI-302',  'Deep Learning and Neural Networks',        'core',     prog_bsai, 3, ['GA-2','GA-5']),
            ('AI3', 'AI-303',  'Computer Vision',                          'core',     prog_bsai, 3, ['GA-2','GA-5']),
            ('AI4', 'AI-304',  'Natural Language Processing',              'core',     prog_bsai, 3, ['GA-2','GA-5']),
            ('AI5', 'AI-401',  'AI Ethics and Society',                    'core',     prog_bsai, 3, ['GA-6','GA-7','GA-8']),
            ('AI6', 'AI-402',  'AI Final Year Project',                    'core',     prog_bsai, 3, ['GA-3','GA-4','GA-9']),
        ]

        # ── QA Courses — Business (real Iqra curriculum) ──────────────────────
        biz_courses = [
            # BBA Core
            ('B1',  'BBA-101', 'Principles of Management',                 'core',     prog_bba, 3, ['GA-B1','GA-B5']),
            ('B2',  'BBA-102', 'Financial Accounting',                     'core',     prog_bba, 3, ['GA-B1','GA-B2']),
            ('B3',  'BBA-201', 'Marketing Management',                     'core',     prog_bba, 3, ['GA-B1','GA-B4']),
            ('B4',  'BBA-202', 'Organizational Behavior',                  'core',     prog_bba, 3, ['GA-B5','GA-B3']),
            ('B5',  'BBA-203', 'Business Mathematics and Statistics',      'core',     prog_bba, 3, ['GA-B1','GA-B2']),
            ('B6',  'BBA-301', 'Human Resource Management',                'core',     prog_bba, 3, ['GA-B5','GA-B3']),
            ('B7',  'BBA-302', 'Financial Management',                     'core',     prog_bba, 3, ['GA-B1','GA-B2']),
            ('B8',  'BBA-303', 'Business Ethics and Corporate Governance', 'core',     prog_bba, 3, ['GA-B3','GA-B8']),
            ('B9',  'BBA-401', 'Strategic Management',                     'core',     prog_bba, 3, ['GA-B1','GA-B2']),
            ('B10', 'BBA-402', 'International Business',                   'core',     prog_bba, 3, ['GA-B7','GA-B2']),
            # BBA Electives
            ('B11', 'BBA-451', 'Entrepreneurship and Innovation',          'elective', prog_bba, 3, ['GA-B6','GA-B2']),
            ('B12', 'BBA-452', 'Digital Marketing',                        'elective', prog_bba, 3, ['GA-B1','GA-B4']),
            # MBA Core
            ('M1',  'MBA-501', 'Managerial Economics',                     'core',     prog_mba, 3, ['GA-B1','GA-B2']),
            ('M2',  'MBA-502', 'Corporate Strategy',                       'core',     prog_mba, 3, ['GA-B1','GA-B2']),
            ('M3',  'MBA-503', 'Leadership and Organizational Change',     'core',     prog_mba, 3, ['GA-B3','GA-B5']),
            ('M4',  'MBA-504', 'Advanced Financial Management',            'core',     prog_mba, 3, ['GA-B1','GA-B2']),
            ('M5',  'MBA-505', 'International Business Strategy',          'core',     prog_mba, 3, ['GA-B7','GA-B2']),
            ('M6',  'MBA-601', 'MBA Research Project',                     'core',     prog_mba, 6, ['GA-B2','GA-B4','GA-B8']),
        ]

        all_courses = cs_courses + biz_courses
        for slug, code, title, ctype, program, credits, ga_ids in all_courses:
            course = Course.objects.create(
                slug=slug, code=code, title=title, type=ctype,
                program=program, department=program.department,
                credit_hours=credits
            )
            course.mapped_gas.set([all_gas[g] for g in ga_ids if g in all_gas])

        self.stdout.write(f'  ✓ Courses ({len(all_courses)} total)')

        # ── Users ─────────────────────────────────────────────────────────────
        # QA
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

        # Instructors
        ins_data = [
            ('dr_ali',    'Dr. Ali',    'Hassan',  'ali.hassan@iqra.edu.pk',    dept_cs,  'INS-CS-001',  'Associate Professor'),
            ('dr_fatima', 'Dr. Fatima', 'Malik',   'fatima.malik@iqra.edu.pk',  dept_cs,  'INS-CS-002',  'Assistant Professor'),
            ('dr_usman',  'Dr. Usman',  'Sheikh',  'usman.sheikh@iqra.edu.pk',  dept_biz, 'INS-BIZ-001', 'Senior Lecturer'),
            ('mr_bilal',  'Mr. Bilal',  'Siddiqui','bilal.siddiqui@iqra.edu.pk',dept_cs,  'INS-CS-003',  'Lecturer'),
        ]
        profiles = {}
        for username, first, last, email, dept, emp_id, designation in ins_data:
            u = User.objects.create(
                username=username, email=email,
                first_name=first, last_name=last,
                role='instructor', password=make_password('instpass123'), is_active=True
            )
            p = InstructorProfile.objects.create(
                user=u, department=dept,
                employee_id=emp_id, designation=designation
            )
            profiles[username] = p

        # Students
        for username, first, last, email, prog, roll, batch in [
            ('ahmed_cs',   'Ahmed',   'Raza',     'ahmed.raza@student.iqra.edu.pk',    prog_bscs, 'FA22-BSCS-0012', 2022),
            ('zara_cs',    'Zara',    'Siddiqui', 'zara.siddiqui@student.iqra.edu.pk', prog_bscs, 'FA22-BSCS-0045', 2022),
            ('hamza_se',   'Hamza',   'Tariq',    'hamza.tariq@student.iqra.edu.pk',   prog_bsse, 'FA22-BSSE-0001', 2022),
            ('aisha_bba',  'Aisha',   'Nawaz',    'aisha.nawaz@student.iqra.edu.pk',   prog_bba,  'FA22-BBA-0001',  2022),
            ('omar_ai',    'Omar',    'Farooq',   'omar.farooq@student.iqra.edu.pk',   prog_bsai, 'FA23-BSAI-0001', 2023),
        ]:
            u = User.objects.create(
                username=username, email=email,
                first_name=first, last_name=last,
                role='student', password=make_password('stupass123'), is_active=True
            )
            Student.objects.create(user=u, program=prog, roll_number=roll, batch_year=batch)

        self.stdout.write('  ✓ Users (2 QA + 4 Instructors + 5 Students)')

        # ── Demo Instructor Course ────────────────────────────────────────────
        demo_course = InstructorCourse.objects.create(
            instructor=profiles['dr_ali'],
            frontend_id='course-demo-1',
            code='CS-301',
            title='Data Structures and Algorithms',
            department=dept_cs,
            program=prog_bscs,
            credit_hours=3,
            clo_count=4,
            selected_grading_system='ready1',
        )

        # Standard Iqra absolute grading scale
        for order, (grade, pct, pts) in enumerate([
            ('A',  90.0, 4.0), ('A-', 85.0, 3.7),
            ('B+', 80.0, 3.3), ('B',  75.0, 3.0), ('B-', 70.0, 2.7),
            ('C+', 65.0, 2.3), ('C',  60.0, 2.0), ('C-', 55.0, 1.7),
            ('D+', 52.0, 1.3), ('D',  50.0, 1.0), ('F',   0.0, 0.0),
        ]):
            GradeScale.objects.create(
                course=demo_course, grade=grade,
                min_percentage=pct, points=pts, order=order
            )

        # Standard Iqra categories
        categories_config = [
            ('Assignments',          15, 3),
            ('Quizzes',              10, 3),
            ('Class Participation',   5, 1),
            ('Class Project',        15, 1),
            ('Presentation',          5, 1),
            ('Mid Term',             20, 1),
            ('Final',                30, 1),
        ]
        unit_config = {
            'Assignments':         [(1,10,5,33.3), (2,10,5,33.3), (3,10,5,33.4)],
            'Quizzes':             [(1,10,5,33.3), (2,10,5,33.3), (3,10,5,33.4)],
            'Class Participation': [(1,10,5,100)],
            'Class Project':       [(1,30,15,100)],
            'Presentation':        [(1,10,5,100)],
            'Mid Term':            [(1,30,15,100)],
            'Final':               [(1,40,20,100)],
        }

        unit_map = {}
        for order, (cat_name, pct, units) in enumerate(categories_config):
            cat = MarksCategory.objects.create(
                course=demo_course, name=cat_name,
                percentage=pct, units=units, order=order
            )
            for unit_no, total, passing, weightage in unit_config[cat_name]:
                u = UnitItem.objects.create(
                    category=cat, unit_no=unit_no,
                    total_marks=total, passing=passing,
                    weightage=weightage,
                    mapped_clos=['CLO-1', 'CLO-2'] if cat_name in ('Assignments','Quizzes') else ['CLO-1','CLO-2','CLO-3','CLO-4']
                )
                unit_map[(cat_name, unit_no)] = u

        # OBE Questions
        q_data = [
            ('q-d1', 'Assignments', 1, 'Q1 — Algorithm Analysis',      5,  ['CLO-1','CLO-2']),
            ('q-d2', 'Assignments', 1, 'Q2 — Sorting Implementation',  5,  ['CLO-3']),
            ('q-d3', 'Quizzes',     1, 'Q1 — Stack and Queue',         10, ['CLO-1','CLO-3','CLO-4']),
            ('q-d4', 'Mid Term',    1, 'Q1 — Trees and Traversal',     15, ['CLO-1','CLO-2']),
            ('q-d5', 'Mid Term',    1, 'Q2 — Graph Algorithms',        15, ['CLO-2','CLO-3']),
        ]
        q_map = {}
        for order, (fid, cat, uno, qname, marks, clos) in enumerate(q_data):
            q = OBEQuestion.objects.create(
                course=demo_course, frontend_id=fid,
                unit_item=unit_map.get((cat, uno)),
                category_name=cat, unit_no=uno,
                question_name=qname, max_marks=marks,
                mapped_clos=clos, order=order
            )
            q_map[fid] = q

        # Students + Marks
        students_seed = [
            {
                'reg_no': 'FA22-BSCS-0012', 'name': 'Ahmed Raza',
                'marks': {
                    ('Assignments',1):8.5,  ('Assignments',2):9.0,  ('Assignments',3):7.5,
                    ('Quizzes',1):7.0,      ('Quizzes',2):8.5,      ('Quizzes',3):9.0,
                    ('Class Participation',1):9.0, ('Class Project',1):26.5,
                    ('Presentation',1):8.0, ('Mid Term',1):24.5, ('Final',1):34.0,
                },
                'obe': {'q-d1':4.5,'q-d2':4.0,'q-d3':8.0,'q-d4':12.5,'q-d5':12.0},
            },
            {
                'reg_no': 'FA22-BSCS-0045', 'name': 'Zara Siddiqui',
                'marks': {
                    ('Assignments',1):9.0,  ('Assignments',2):8.0,  ('Assignments',3):8.5,
                    ('Quizzes',1):8.0,      ('Quizzes',2):7.5,      ('Quizzes',3):6.5,
                    ('Class Participation',1):8.0, ('Class Project',1):25.0,
                    ('Presentation',1):9.0, ('Mid Term',1):22.0, ('Final',1):32.5,
                },
                'obe': {'q-d1':5.0,'q-d2':3.5,'q-d3':7.5,'q-d4':11.0,'q-d5':11.0},
            },
            {
                'reg_no': 'FA22-BSCS-0089', 'name': 'Bilal Ahmad',
                'marks': {
                    ('Assignments',1):7.5,  ('Assignments',2):7.0,  ('Assignments',3):8.0,
                    ('Quizzes',1):6.0,      ('Quizzes',2):5.0,      ('Quizzes',3):7.0,
                    ('Class Participation',1):7.0, ('Class Project',1):22.0,
                    ('Presentation',1):7.5, ('Mid Term',1):19.5, ('Final',1):28.0,
                },
                'obe': {'q-d1':3.5,'q-d2':2.5,'q-d3':5.0,'q-d4':9.5,'q-d5':10.0},
            },
            {
                'reg_no': 'FA22-BSCS-0102', 'name': 'Maryam Khan',
                'marks': {
                    ('Assignments',1):9.5,  ('Assignments',2):9.0,  ('Assignments',3):9.0,
                    ('Quizzes',1):9.0,      ('Quizzes',2):8.5,      ('Quizzes',3):9.5,
                    ('Class Participation',1):10.0,('Class Project',1):28.0,
                    ('Presentation',1):9.5, ('Mid Term',1):27.0, ('Final',1):37.0,
                },
                'obe': {'q-d1':5.0,'q-d2':4.5,'q-d3':9.5,'q-d4':13.5,'q-d5':13.0},
            },
        ]

        for s_data in students_seed:
            student = CourseStudent.objects.create(
                course=demo_course, reg_no=s_data['reg_no'], name=s_data['name']
            )
            for (cat_name, unit_no), score in s_data['marks'].items():
                unit_obj = unit_map.get((cat_name, unit_no))
                if unit_obj:
                    StudentMark.objects.create(student=student, unit_item=unit_obj, score=score)
            for q_id, score in s_data['obe'].items():
                if q_id in q_map:
                    OBEStudentMark.objects.create(student=student, question=q_map[q_id], score=score)

        self.stdout.write('  ✓ Demo Course (DS&A) with 4 students + full marks')

        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS('\n✅  Seed complete!'))
        self.stdout.write(f'   Departments       : {Department.objects.count()}')
        self.stdout.write(f'   Programs          : {Program.objects.count()}')
        self.stdout.write(f'   Graduate Attrs    : {GraduateAttribute.objects.count()}')
        self.stdout.write(f'   Program Objectives: {ProgramObjective.objects.count()}')
        self.stdout.write(f'   QA Courses        : {Course.objects.count()}')
        self.stdout.write(f'   Instructor Courses: {InstructorCourse.objects.count()}')
        self.stdout.write(f'   Categories        : {MarksCategory.objects.count()}')
        self.stdout.write(f'   Unit Items        : {UnitItem.objects.count()}')
        self.stdout.write(f'   OBE Questions     : {OBEQuestion.objects.count()}')
        self.stdout.write(f'   Students          : {CourseStudent.objects.count()}')
        self.stdout.write(f'   Student Marks     : {StudentMark.objects.count()}')
        self.stdout.write(f'   OBE Marks         : {OBEStudentMark.objects.count()}')
        self.stdout.write(f'   Users             : {User.objects.count()}')
        self.stdout.write('\n  Credentials:')
        self.stdout.write('   qa_computing / qapass123   (QA — Computing)')
        self.stdout.write('   qa_business  / qapass123   (QA — Business)')
        self.stdout.write('   dr_ali       / instpass123 (Instructor — Associate Professor)')
        self.stdout.write('   dr_fatima    / instpass123 (Instructor — Assistant Professor)')
        self.stdout.write('   ahmed_cs     / stupass123  (Student — BSCS)')
