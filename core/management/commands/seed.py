from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from core.models import (
    User, Department, Program, ProgramObjective, POGAMapping,
    GraduateAttribute, QAProfile, InstructorProfile, Student,
    Course, InstructorCourse, GradeScale, MarksCategory, UnitItem,
    OBEQuestion, CourseStudent, StudentMark, OBEStudentMark,
    AdmissionStudent,
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
            AdmissionStudent, Student, InstructorProfile, QAProfile,
            Program, Department,
        ]:
            model.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        self.stdout.write('  ✓ Cleared old data')

        # ── Departments ───────────────────────────────────────────────────────
        dept_cs = Department.objects.create(
            slug='computing',
            name='Department of Computing and Technology',
            vision='To emerge as a global leader in computer science research and education by driving technological innovation, solving real-world challenges, and empowering future leaders.',
            mission='To foster academic excellence and cutting-edge research, positioning our department as a global leader in computer science innovation. By instilling ethical values, technical prowess, and interdisciplinary knowledge, we prepare students for impactful careers in the field.',
        )
        dept_biz = Department.objects.create(
            slug='business',
            name='Department of Business Administration',
            vision='To be a leading business school recognized globally for nurturing entrepreneurial mindsets and ethical leadership in the corporate world.',
            mission='To empower students with innovative business education, pioneering research capabilities, and ethical principles designed to create future business leaders.',
        )
        self.stdout.write('  ✓ Departments')

        # ── Programs ──────────────────────────────────────────────────────────
        prog_bscs = Program.objects.create(
            slug='bscs', name='Bachelor of Science in Computer Science',
            code='BSCS', department=dept_cs,
            vision='To produce computer science graduates of international standards with state-of-the-art skills.',
            mission='To empower students with deep scientific computer knowledge, preparing them for leading-edge industry roles.',
        )
        prog_bba = Program.objects.create(
            slug='bba', name='Bachelor of Business Administration',
            code='BBA', department=dept_biz,
            vision='To cultivate business leaders who drive organizational success with integrity and innovation.',
            mission='To deliver a comprehensive business curriculum that integrates theory, practice, and ethical leadership.',
        )
        self.stdout.write('  ✓ Programs')

        # ── Graduate Attributes — exact match to frontend fallback ─────────────
        all_gas = {}
        cs_gas = [
            ('GA-1',  'Academic Education',
             'Completion of an accredited program of study designed to prepare graduates as computing professionals.'),
            ('GA-2',  'Knowledge for Solving Computing Problems',
             'Apply knowledge of computing fundamentals, mathematics, science, and domain knowledge to the abstraction and conceptualization of computing models.'),
            ('GA-3',  'Problem Analysis',
             'Identify and solve complex computing problems reaching substantiated conclusions using fundamental principles of mathematics and computing sciences.'),
            ('GA-4',  'Design/Development of Solutions',
             'Design and evaluate solutions for complex computing problems, and design and evaluate systems, components, or processes that meet specified needs.'),
            ('GA-5',  'Modern Tool Usage',
             'Create, select, or adapt and apply appropriate techniques, resources, and modern computing tools to complex computing activities.'),
            ('GA-6',  'Individual and Team Work',
             'Function effectively as an individual and as a member or leader of a team in multidisciplinary settings.'),
            ('GA-7',  'Communication',
             'Communicate effectively with the computing community about complex computing activities by being able to comprehend and write effective reports, design documentation, make effective presentations.'),
            ('GA-8',  'Computing Professionalism and Society',
             'Understand and assess societal, health, safety, legal, and cultural issues within local and global contexts, and the consequential responsibilities relevant to professional computing practice.'),
            ('GA-9',  'Ethics',
             'Understand and commit to professional ethics, responsibilities, and norms of professional computing practice.'),
            ('GA-10', 'Life-long Learning',
             'Recognize the need, and have the ability, to engage in independent learning for continual development as a computing professional.'),
        ]
        biz_gas = [
            ('GA-B1', 'Business Analytics & Decision Making',
             'Execute comprehensive business analysis and apply quantitative tools for strategic decision support.'),
            ('GA-B2', 'Leadership & Teamwork',
             'Foster strong collaborative performance, conflict resolution, and motivational team frameworks within workspaces.'),
            ('GA-B3', 'Strategic Thinking',
             'Synthesize market trends, competitive intelligence, and internal structures to deploy agile business vision.'),
            ('GA-B4', 'Financial Literacy',
             'Evaluate balance sheets, corporate portfolios, and financial statements to drive corporate value addition.'),
            ('GA-B5', 'Corporate Social Responsibility & Ethics',
             'Demonstrate deep compliance, corporate transparency, and standard professional ethics in corporate systems.'),
            ('GA-B6', 'Communication & Presenting',
             'Deliver highly structured business communications, elevator pitches, and expert corporate reporting values.'),
            ('GA-B7', 'Critical Advisory',
             'Troubleshoot complex business cases and offer sustainable, optimized pathways to enterprise models.'),
            ('GA-B8', 'Business Enterprise',
             'Exhibit high entrepreneurial alertness, business opportunity detection traits, and adaptive startup frameworks.'),
        ]
        for ga_id, name, desc in cs_gas:
            all_gas[ga_id] = GraduateAttribute.objects.create(
                ga_id=ga_id, name=name, description=desc, department=dept_cs
            )
        for ga_id, name, desc in biz_gas:
            all_gas[ga_id] = GraduateAttribute.objects.create(
                ga_id=ga_id, name=name, description=desc, department=dept_biz
            )
        self.stdout.write('  ✓ Graduate Attributes (10 CS + 8 Business)')

        # ── Program Objectives — exact match to frontend fallback ─────────────
        po_data = {
            prog_bscs: [
                ('PO1', 'Establishing in-depth understanding of theoretical concepts related to computer science.',
                 ['GA-1', 'GA-2']),
                ('PO2', 'Applying core Computer Science knowledge and analytical skills to optimally solve real-world problems.',
                 ['GA-1', 'GA-2', 'GA-3', 'GA-4', 'GA-5']),
                ('PO3', 'Imbuing quest for learning and engaging in continuous professional development in the field of computer science by carrying research and adopting professional practices.',
                 ['GA-3', 'GA-4', 'GA-6', 'GA-7', 'GA-8', 'GA-10']),
                ('PO4', 'Developing the ability to work in a multi-disciplinary and multi cultural environment in teams incorporating soft skills and maintaining high ethical standards.',
                 ['GA-6', 'GA-7', 'GA-9']),
            ],
            prog_bba: [
                ('PO1', 'Mastering Core Business Management Skills and Analytical Tools.',
                 ['GA-B1', 'GA-B4']),
                ('PO2', 'Strategic planning, operations synthesis, and ethical decision modeling.',
                 ['GA-B2', 'GA-B3', 'GA-B5']),
                ('PO3', 'Fostering innovative business development strategies and executive communication.',
                 ['GA-B3', 'GA-B6', 'GA-B8']),
                ('PO4', 'Developing adaptive management capabilities in multi-dimensional market climates.',
                 ['GA-B2', 'GA-B7']),
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
                            program_objective=po, graduate_attribute=all_gas[ga_id]
                        )
        self.stdout.write('  ✓ Program Objectives + PO-GA Mappings')

        # ── Courses — exact match to frontend fallback ─────────────────────────
        cs_courses = [
            # Core BSCS (C1-C37)
            ('C1',  'CMC111',   'Programming Fundamentals',                      'core',     ['GA-1','GA-2','GA-4']),
            ('C2',  'GER111',   'Application of Information & Communication Technologies','core',['GA-1','GA-2','GA-5']),
            ('C3',  'GER121',   'Functional English',                            'core',     ['GA-1','GA-7']),
            ('C4',  'GER131',   'Calculus and Analytic Geometry',                'core',     ['GA-1','GA-2','GA-3']),
            ('C5',  'GER141',   'Islamic Studies',                               'core',     ['GA-1','GA-6','GA-8','GA-9']),
            ('C6',  'GER151',   'Natural Science (Applied Physics)',              'core',     ['GA-1','GA-2']),
            ('C7',  'MTE111',   'Multivariable Calculus',                        'core',     ['GA-1','GA-2','GA-3']),
            ('C8',  'CMC112',   'Object Oriented Programming',                   'core',     ['GA-1','GA-2','GA-4']),
            ('C9',  'CMC121',   'Digital Logic Design',                          'core',     ['GA-1','GA-2','GA-3']),
            ('C10', 'GER122',   'Expository Writing',                            'core',     ['GA-1','GA-6','GA-7']),
            ('C11', 'GER132',   'Discrete Structures',                           'core',     ['GA-1','GA-2','GA-3']),
            ('C12', 'GER142',   'Ideology and Constitution of Pakistan',         'core',     ['GA-1','GA-8','GA-9','GA-10']),
            ('C13', 'MTE212',   'Probability & Statistics',                      'core',     ['GA-1','GA-2','GA-3']),
            ('C14', 'CMC222',   'Computer Organization & Assembly Language',     'core',     ['GA-1','GA-2','GA-3']),
            ('C15', 'CMC251',   'Data Structures',                               'core',     ['GA-1','GA-2','GA-3','GA-5']),
            ('C16', 'CSC252',   'Theory of Automata',                            'core',     ['GA-1','GA-2','GA-3','GA-4']),
            ('C17', 'CMC261',   'Computer Networks',                             'core',     ['GA-1','GA-2','GA-3']),
            ('C18', 'MTE213',   'Linear Algebra',                                'core',     ['GA-1','GA-2','GA-3']),
            ('C19', 'MTE221',   'Technical & Business Writing',                  'core',     ['GA-1','GA-6','GA-8']),
            ('C20', 'CSC223',   'Computer Architecture',                         'core',     ['GA-1','GA-2','GA-5']),
            ('C21', 'CMC241',   'Operating Systems',                             'core',     ['GA-1','GA-2','GA-3']),
            ('C22', 'CMC253',   'Analysis of Algorithms',                        'core',     ['GA-1','GA-2','GA-3','GA-4']),
            ('C23', 'GER261',   'Introduction to Management',                    'core',     ['GA-1','GA-3','GA-6']),
            ('C24', 'CMC331',   'Database Systems',                              'core',     ['GA-1','GA-2','GA-3','GA-5']),
            ('C25', 'CSC354',   'Compiler Construction',                         'core',     ['GA-1','GA-2','GA-3','GA-4']),
            ('C26', 'CMC362',   'Information Security',                          'core',     ['GA-1','GA-2','GA-3','GA-4']),
            ('C27', 'CMC371',   'Software Engineering',                          'core',     ['GA-1','GA-2','GA-3']),
            ('C28', 'CSC332',   'Advance Database Management Systems',           'core',     ['GA-1','GA-2','GA-3','GA-5']),
            ('C29', 'CMC381',   'Artificial Intelligence',                       'core',     ['GA-1','GA-2','GA-3','GA-4','GA-5']),
            ('C30', 'CSC382',   'HCI & Computer Graphics',                       'core',     ['GA-1','GA-3','GA-4','GA-5']),
            ('C31', 'ESC311',   'Introduction to Marketing',                     'core',     ['GA-1','GA-7','GA-8','GA-9']),
            ('C32', 'CSC442',   'Parallel & Distributed Computing',              'core',     ['GA-1','GA-2','GA-4','GA-5']),
            ('C33', 'GER462',   'Technopreneurship',                             'core',     ['GA-1','GA-7','GA-9','GA-10']),
            ('C34', 'CMC491',   'Final Year Project - I',                        'core',     ['GA-1']),
            ('C35', 'GER443',   'Civics and Community Engagement',               'core',     ['GA-1','GA-7','GA-8','GA-9']),
            ('C36', 'GER463',   'Professional Practices',                        'core',     ['GA-1','GA-8','GA-9','GA-10']),
            ('C37', 'CMC492',   'Final Year Project - II',                       'core',     ['GA-1','GA-2','GA-3','GA-4','GA-5','GA-6','GA-7','GA-8','GA-9','GA-10']),
            # Electives
            ('C38', 'CSC467',   'Internet of Things',                            'elective', ['GA-1','GA-2','GA-3','GA-4']),
            ('C39', 'CMC381-E', 'Artificial Intelligence (Elective)',            'elective', ['GA-1','GA-2','GA-4','GA-5']),
            ('C40', 'CSC436',   'Data Warehousing & Data Mining',                'elective', ['GA-1','GA-2','GA-3','GA-7','GA-10']),
            ('C41', 'CSC479',   'Machine Learning',                              'elective', ['GA-1','GA-2','GA-4','GA-5']),
            ('C42', 'CSC435',   'Mobile Application Development',                'elective', ['GA-1','GA-2','GA-3']),
            ('C43', 'CSC321',   'Embedded Systems',                              'elective', ['GA-1','GA-2','GA-5']),
            ('C44', 'CSC478',   'Routing and Switching',                         'elective', ['GA-1','GA-2','GA-3','GA-4']),
        ]
        biz_courses = [
            ('CB1',  'BUS101',  'Principles of Management',                      'core',     ['GA-B2','GA-B3','GA-B6']),
            ('CB2',  'MKT111',  'Principles of Marketing',                       'core',     ['GA-B3','GA-B6','GA-B8']),
            ('CB3',  'ACC121',  'Financial Accounting',                          'core',     ['GA-B1','GA-B4']),
            ('CB4',  'HRM211',  'Human Resource Management',                     'core',     ['GA-B2','GA-B5','GA-B6']),
            ('CB5',  'ECO131',  'Microeconomics',                                'core',     ['GA-B1','GA-B3']),
            ('CB6',  'MGT222',  'Organizational Behavior',                       'core',     ['GA-B2','GA-B5','GA-B6']),
            ('CB7',  'FIN311',  'Business Finance',                              'core',     ['GA-B1','GA-B4']),
            ('CB8',  'MGT331',  'Strategic Management',                          'core',     ['GA-B3','GA-B5','GA-B7','GA-B8']),
            ('CB9',  'BUS491',  'BBA Capstone Project - I',                      'core',     ['GA-B1','GA-B2','GA-B3','GA-B6']),
            ('CB10', 'BUS492',  'BBA Capstone Project - II',                     'core',     ['GA-B1','GA-B2','GA-B3','GA-B4','GA-B5','GA-B6','GA-B7','GA-B8']),
            ('CB11', 'ENTR451', 'Social Entrepreneurship',                       'elective', ['GA-B5','GA-B8']),
            ('CB12', 'FIN462',  'Investment Portfolio Analysis',                 'elective', ['GA-B1','GA-B4','GA-B7']),
        ]
        for slug, code, title, ctype, ga_ids in cs_courses:
            c = Course.objects.create(
                slug=slug, code=code, title=title, type=ctype,
                program=prog_bscs, department=dept_cs, credit_hours=3
            )
            c.mapped_gas.set([all_gas[g] for g in ga_ids if g in all_gas])

        for slug, code, title, ctype, ga_ids in biz_courses:
            c = Course.objects.create(
                slug=slug, code=code, title=title, type=ctype,
                program=prog_bba, department=dept_biz, credit_hours=3
            )
            c.mapped_gas.set([all_gas[g] for g in ga_ids if g in all_gas])

        self.stdout.write('  ✓ Courses (44 Computing + 12 Business)')

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

        # Admission officer
        admission_user = User.objects.create(
            username='admission', email='admission@iqra.edu.pk',
            first_name='Admission', last_name='Officer',
            role='admission', password=make_password('admpass123'), is_active=True
        )

        # Instructors
        instructor_profiles = {}
        for username, first, last, email, dept, emp_id, designation in [
            ('dr_ali',    'Ali',    'Hassan', 'ali.hassan@iqra.edu.pk',   dept_cs,  'INS-CS-001', 'Associate Professor'),
            ('dr_fatima', 'Fatima', 'Malik',  'fatima.malik@iqra.edu.pk', dept_cs,  'INS-CS-002', 'Assistant Professor'),
            ('dr_usman',  'Usman',  'Sheikh', 'usman.sheikh@iqra.edu.pk', dept_biz, 'INS-BIZ-001','Senior Lecturer'),
        ]:
            u = User.objects.create(
                username=username, email=email,
                first_name=first, last_name=last,
                role='instructor', password=make_password('instpass123'), is_active=True
            )
            p = InstructorProfile.objects.create(
                user=u, department=dept, employee_id=emp_id, designation=designation
            )
            instructor_profiles[username] = p

        self.stdout.write('  ✓ Users (2 QA, 1 Admission, 3 Instructors)')

        # ── Admission Students ────────────────────────────────────────────────
        admission_students = [
            ('FA22-BSCS-0012', 'Abdur Rehman Khalid', dept_cs, prog_bscs, 'Fall'),
            ('FA22-BSCS-0045', 'Syeda Fatima Alvi',   dept_cs, prog_bscs, 'Fall'),
            ('FA22-BSCS-0089', 'Zayan Ahmed Khan',    dept_cs, prog_bscs, 'Fall'),
            ('FA22-BSCS-0104', 'Misha Farooq',        dept_cs, prog_bscs, 'Fall'),
            ('FA22-BBA-0021',  'Bilal Hussain',        dept_biz, prog_bba, 'Spring'),
            ('FA22-BBA-0035',  'Amna Tariq',           dept_biz, prog_bba, 'Fall'),
        ]
        for reg_no, name, dept, prog, batch in admission_students:
            AdmissionStudent.objects.create(
                reg_no=reg_no, name=name,
                department=dept, program=prog, batch=batch
            )
        self.stdout.write('  ✓ Admission Students (6 demo students)')

        # ── Demo Instructor Course ────────────────────────────────────────────
        dr_ali = instructor_profiles['dr_ali']
        ic = InstructorCourse.objects.create(
            instructor=dr_ali, frontend_id='course-demo-1',
            code='CMC371', title='Software Engineering',
            course_type='Theory',
            department=dept_cs, program=prog_bscs,
            credit_hours=3, clo_count=4, selected_grading_system='ready1',
        )

        for order, (grade, pct, pts) in enumerate([
            ('A',90,4.0),('A-',85,3.7),('B+',80,3.3),('B',75,3.0),
            ('B-',70,2.7),('C+',65,2.3),('C',60,2.0),('C-',55,1.7),
            ('D',50,1.0),('F',0,0.0),
        ]):
            GradeScale.objects.create(
                course=ic, grade=grade, min_percentage=pct, points=pts, order=order
            )

        categories_def = [
            ('Assignments',15,3,[(1,10,5,33.3,['CLO-1','CLO-2']),(2,10,5,33.3,['CLO-2','CLO-3']),(3,10,5,33.4,['CLO-1','CLO-3'])]),
            ('Quizzes',10,3,[(1,10,5,33.3,['CLO-1','CLO-2']),(2,10,5,33.3,['CLO-3','CLO-4']),(3,10,5,33.4,['CLO-1','CLO-4'])]),
            ('Class Participation',5,1,[(1,10,5,100,['CLO-1','CLO-2','CLO-3','CLO-4'])]),
            ('Class Project',15,1,[(1,30,15,100,['CLO-2','CLO-3','CLO-4'])]),
            ('Presentation',5,1,[(1,10,5,100,['CLO-1','CLO-2'])]),
            ('Lab Project',0,0,[]),
            ('Problem Based Learning',0,0,[]),
            ('Complex Problem',0,0,[]),
            ('Other Activities',0,0,[]),
            ('Viva',0,0,[]),
            ('Lab Performance',0,0,[]),
            ('Lab Reports',0,0,[]),
            ('Mid Term',20,1,[(1,30,15,100,['CLO-1','CLO-2','CLO-3'])]),
            ('Final',30,1,[(1,40,20,100,['CLO-1','CLO-2','CLO-3','CLO-4'])]),
        ]
        unit_map = {}
        for order, (cat_name, pct, units, unit_list) in enumerate(categories_def):
            cat = MarksCategory.objects.create(
                course=ic, name=cat_name, percentage=pct, units=units, order=order
            )
            for unit_no, total, passing, weightage, clos in unit_list:
                u = UnitItem.objects.create(
                    category=cat, unit_no=unit_no,
                    total_marks=total, passing=passing,
                    weightage=weightage, mapped_clos=clos
                )
                unit_map[(cat_name, unit_no)] = u

        q_map = {}
        for fid, cat, uno, qname, mm, clos, ord_ in [
            ('q-demo-1','Assignments',1,'Q1 - Problem Identification',5,['CLO-1','CLO-2'],0),
            ('q-demo-2','Assignments',1,'Q2 - Solution Design',5,['CLO-3'],1),
            ('q-demo-3','Quizzes',1,'Q1 - Concept Application',10,['CLO-1','CLO-3','CLO-4'],0),
            ('q-demo-4','Mid Term',1,'Q1 - Analysis',15,['CLO-1','CLO-2'],0),
            ('q-demo-5','Mid Term',1,'Q2 - System Design',15,['CLO-2','CLO-3'],1),
        ]:
            q_map[fid] = OBEQuestion.objects.create(
                course=ic, frontend_id=fid,
                unit_item=unit_map.get((cat, uno)),
                category_name=cat, unit_no=uno,
                question_name=qname, max_marks=mm,
                mapped_clos=clos, order=ord_
            )

        students_seed = [
            ('FA22-BSCS-0012','Abdur Rehman Khalid',
             {('Assignments',1):8.5,('Assignments',2):9.0,('Assignments',3):7.5,
              ('Quizzes',1):7.0,('Quizzes',2):8.5,('Quizzes',3):9.0,
              ('Class Participation',1):9.0,('Class Project',1):26.5,
              ('Presentation',1):8.0,('Mid Term',1):24.5,('Final',1):34.0},
             {'q-demo-1':4.5,'q-demo-2':4.0,'q-demo-3':8.0,'q-demo-4':12.5,'q-demo-5':12.0}),
            ('FA22-BSCS-0045','Syeda Fatima Alvi',
             {('Assignments',1):9.0,('Assignments',2):8.0,('Assignments',3):8.5,
              ('Quizzes',1):8.0,('Quizzes',2):7.5,('Quizzes',3):6.5,
              ('Class Participation',1):8.0,('Class Project',1):25.0,
              ('Presentation',1):9.0,('Mid Term',1):22.0,('Final',1):32.5},
             {'q-demo-1':5.0,'q-demo-2':3.5,'q-demo-3':7.5,'q-demo-4':11.0,'q-demo-5':11.0}),
            ('FA22-BSCS-0089','Zayan Ahmed Khan',
             {('Assignments',1):7.5,('Assignments',2):7.0,('Assignments',3):8.0,
              ('Quizzes',1):6.0,('Quizzes',2):5.0,('Quizzes',3):7.0,
              ('Class Participation',1):7.0,('Class Project',1):22.0,
              ('Presentation',1):7.5,('Mid Term',1):19.5,('Final',1):28.0},
             {'q-demo-1':3.5,'q-demo-2':2.5,'q-demo-3':5.0,'q-demo-4':9.5,'q-demo-5':10.0}),
        ]
        for reg_no, name, marks, obe in students_seed:
            s = CourseStudent.objects.create(course=ic, reg_no=reg_no, name=name)
            for (cat, uno), score in marks.items():
                u = unit_map.get((cat, uno))
                if u:
                    StudentMark.objects.create(student=s, unit_item=u, score=score)
            for qid, score in obe.items():
                OBEStudentMark.objects.create(student=s, question=q_map[qid], score=score)

        self.stdout.write('  ✓ Demo Instructor Course + Marks')

        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS('\n✅  Seed complete!'))
        self.stdout.write(f'   Departments      : {Department.objects.count()}')
        self.stdout.write(f'   Programs         : {Program.objects.count()}')
        self.stdout.write(f'   Graduate Attrs   : {GraduateAttribute.objects.count()}')
        self.stdout.write(f'   QA Courses       : {Course.objects.count()}')
        self.stdout.write(f'   Admission Students: {AdmissionStudent.objects.count()}')
        self.stdout.write(f'   Instructor Crss  : {InstructorCourse.objects.count()}')
        self.stdout.write(f'   Users            : {User.objects.count()}')
        self.stdout.write('\n  Login credentials:')
        self.stdout.write('   qa_computing / qapass123   → QA (Computing)')
        self.stdout.write('   qa_business  / qapass123   → QA (Business)')
        self.stdout.write('   admission    / admpass123  → Admission Officer')
        self.stdout.write('   dr_ali       / instpass123 → Instructor')
