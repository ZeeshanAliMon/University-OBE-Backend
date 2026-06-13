from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from core.models import (
    User, Department, Program, ProgramObjective, POGAMapping,
    GraduateAttribute, QAProfile, InstructorProfile, Student,
    Course, InstructorCourse,
)


class Command(BaseCommand):
    help = 'Seed the database with placeholder data'

    def handle(self, *args, **kwargs):
        self.stdout.write('🌱  Seeding database ...')

        # Clean slate
        POGAMapping.objects.all().delete()
        ProgramObjective.objects.all().delete()
        InstructorCourse.objects.all().delete()
        Course.objects.all().delete()
        GraduateAttribute.objects.all().delete()
        Student.objects.all().delete()
        InstructorProfile.objects.all().delete()
        QAProfile.objects.all().delete()
        Program.objects.all().delete()
        Department.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        self.stdout.write('  ✓ Cleared old data')

        # Departments
        dept_cs, _ = Department.objects.get_or_create(
            slug='computing',
            defaults=dict(
                name='Department of Computing and Technology',
                vision='To be a globally recognized department producing world-class computing professionals.',
                mission='To deliver high-quality computing education grounded in outcome-based learning.',
            )
        )
        dept_biz, _ = Department.objects.get_or_create(
            slug='business',
            defaults=dict(
                name='Department of Business Administration',
                vision='To nurture future business leaders who create sustainable value.',
                mission='To provide rigorous, practice-oriented business education.',
            )
        )
        self.stdout.write('  ✓ Departments')

        # Programs
        prog_bscs, _ = Program.objects.get_or_create(
            slug='bscs',
            defaults=dict(name='Bachelor of Science in Computer Science', code='BSCS', department=dept_cs,
                          vision='To produce innovative, ethical CS graduates.', mission='To provide rigorous CS foundations.')
        )
        prog_bsse, _ = Program.objects.get_or_create(
            slug='bsse',
            defaults=dict(name='Bachelor of Science in Software Engineering', code='BSSE', department=dept_cs,
                          vision='To develop quality software engineers.', mission='To instill SE principles and ethics.')
        )
        prog_bba, _ = Program.objects.get_or_create(
            slug='bba',
            defaults=dict(name='Bachelor of Business Administration', code='BBA', department=dept_biz,
                          vision='To cultivate business leaders with integrity.', mission='To deliver comprehensive business curriculum.')
        )
        prog_mba, _ = Program.objects.get_or_create(
            slug='mba',
            defaults=dict(name='Master of Business Administration', code='MBA', department=dept_biz,
                          vision='To produce strategic thinkers for global challenges.', mission='To develop advanced managerial capabilities.')
        )
        self.stdout.write('  ✓ Programs')

        # Graduate Attributes
        all_gas = {}
        ga_data = [
            ('GA-1',    'Academic Education',       'Apply knowledge of computing and mathematics.',                    dept_cs,  prog_bscs),
            ('GA-2',    'Problem Analysis',          'Identify and analyse complex computing problems.',                 dept_cs,  prog_bscs),
            ('GA-3',    'Design and Development',    'Design and develop solutions for complex computing problems.',     dept_cs,  prog_bscs),
            ('GA-4',    'Investigation',             'Investigate complex problems using research-based knowledge.',     dept_cs,  prog_bscs),
            ('GA-5',    'Modern Tool Usage',         'Apply modern computing tools and techniques.',                     dept_cs,  prog_bscs),
            ('GA-6',    'Ethics',                    'Apply ethical principles and professional responsibilities.',      dept_cs,  prog_bscs),
            ('GA-SE-1', 'Engineering Knowledge',     'Apply software engineering principles.',                          dept_cs,  prog_bsse),
            ('GA-SE-2', 'Problem Analysis',          'Identify and analyse complex SE problems.',                       dept_cs,  prog_bsse),
            ('GA-SE-3', 'Design & Architecture',     'Design software architectures meeting requirements.',             dept_cs,  prog_bsse),
            ('GA-SE-4', 'Team Collaboration',        'Function effectively in diverse teams.',                          dept_cs,  prog_bsse),
            ('GA-SE-5', 'Project Management',        'Demonstrate knowledge of project management.',                    dept_cs,  prog_bsse),
            ('GA-SE-6', 'Ethics & Professionalism',  'Apply professional ethics in SE practice.',                      dept_cs,  prog_bsse),
            ('GA-B1',   'Business Knowledge',        'Demonstrate foundational business knowledge.',                    dept_biz, prog_bba),
            ('GA-B2',   'Critical Thinking',         'Analyse business problems using quantitative methods.',           dept_biz, prog_bba),
            ('GA-B3',   'Communication',             'Communicate effectively in written and oral formats.',            dept_biz, prog_bba),
            ('GA-B4',   'Leadership',                'Demonstrate leadership and team management skills.',              dept_biz, prog_bba),
            ('GA-B5',   'Ethics & Social Resp.',     'Apply ethical standards in business decisions.',                  dept_biz, prog_bba),
            ('GA-B6',   'Entrepreneurship',          'Identify entrepreneurial opportunities.',                         dept_biz, prog_bba),
            ('GA-M1',   'Strategic Management',      'Formulate competitive business strategies.',                      dept_biz, prog_mba),
            ('GA-M2',   'Financial Acumen',          'Apply advanced financial analysis.',                              dept_biz, prog_mba),
            ('GA-M3',   'Global Business',           'Evaluate global business environments.',                         dept_biz, prog_mba),
            ('GA-M4',   'Leadership & Change',       'Lead organisational change initiatives.',                         dept_biz, prog_mba),
        ]
        for ga_id, name, desc, dept, prog in ga_data:
            ga, _ = GraduateAttribute.objects.get_or_create(
                ga_id=ga_id, defaults=dict(name=name, description=desc, department=dept, program=prog)
            )
            all_gas[ga_id] = ga
        self.stdout.write('  ✓ Graduate Attributes')

        # POs
        po_data = {
            prog_bscs: [
                ('PO1', 'Apply knowledge of mathematics and computing to solve complex problems.',    ['GA-1', 'GA-2']),
                ('PO2', 'Design and implement software systems meeting specified requirements.',       ['GA-3', 'GA-5']),
                ('PO3', 'Conduct investigation of complex problems using research-based methods.',    ['GA-4', 'GA-2']),
                ('PO4', 'Apply professional ethics and responsibilities in computing practice.',      ['GA-6']),
            ],
            prog_bsse: [
                ('PO1', 'Apply SE principles to design, develop, and maintain software systems.',    ['GA-SE-1', 'GA-SE-3']),
                ('PO2', 'Analyse user requirements and translate them into reliable solutions.',      ['GA-SE-2', 'GA-SE-3']),
                ('PO3', 'Work effectively in teams using industry-standard tools.',                  ['GA-SE-4', 'GA-SE-5']),
                ('PO4', 'Demonstrate ethical conduct in software engineering.',                      ['GA-SE-6']),
            ],
            prog_bba: [
                ('PO1', 'Demonstrate comprehensive knowledge across core business functions.',        ['GA-B1', 'GA-B2']),
                ('PO2', 'Communicate business insights clearly to diverse audiences.',               ['GA-B3']),
                ('PO3', 'Lead and manage teams with sound judgment.',                               ['GA-B4', 'GA-B5']),
                ('PO4', 'Identify and develop entrepreneurial ventures.',                            ['GA-B6', 'GA-B2']),
            ],
            prog_mba: [
                ('PO1', 'Formulate competitive strategies creating sustainable value.',              ['GA-M1', 'GA-M2']),
                ('PO2', 'Evaluate global market opportunities and mitigate risks.',                 ['GA-M3', 'GA-M1']),
                ('PO3', 'Lead transformational change with stakeholder alignment.',                 ['GA-M4', 'GA-M1']),
                ('PO4', 'Apply advanced financial models for investment decisions.',                ['GA-M2']),
            ],
        }
        for program, pos in po_data.items():
            for code, desc, ga_ids in pos:
                po, _ = ProgramObjective.objects.get_or_create(
                    program=program, code=code, defaults={'description': desc}
                )
                POGAMapping.objects.filter(program_objective=po).delete()
                for ga_id in ga_ids:
                    if ga_id in all_gas:
                        POGAMapping.objects.get_or_create(program_objective=po, graduate_attribute=all_gas[ga_id])
        self.stdout.write('  ✓ Program Objectives + PO-GA Mappings')

        # Courses
        course_data = [
            ('C1',  'CMC111', 'Programming Fundamentals',           'core',     prog_bscs, dept_cs,  ['GA-1', 'GA-2']),
            ('C2',  'CMC211', 'Object Oriented Programming',        'core',     prog_bscs, dept_cs,  ['GA-1', 'GA-3']),
            ('C3',  'CMC311', 'Data Structures and Algorithms',     'core',     prog_bscs, dept_cs,  ['GA-2', 'GA-3', 'GA-4']),
            ('C4',  'CMC321', 'Database Systems',                   'core',     prog_bscs, dept_cs,  ['GA-3', 'GA-5']),
            ('C5',  'CMC411', 'Artificial Intelligence',            'core',     prog_bscs, dept_cs,  ['GA-4', 'GA-5']),
            ('C6',  'CMC412', 'Machine Learning',                   'elective', prog_bscs, dept_cs,  ['GA-4', 'GA-5']),
            ('C7',  'CMC322', 'Computer Networks',                  'core',     prog_bscs, dept_cs,  ['GA-1', 'GA-5']),
            ('C8',  'CMC421', 'Final Year Project',                 'core',     prog_bscs, dept_cs,  ['GA-3', 'GA-4', 'GA-6']),
            ('SE1', 'SWE111', 'Introduction to Software Engineering','core',    prog_bsse, dept_cs,  ['GA-SE-1', 'GA-SE-2']),
            ('SE2', 'SWE211', 'Software Requirements Engineering',   'core',    prog_bsse, dept_cs,  ['GA-SE-2', 'GA-SE-3']),
            ('SE3', 'SWE221', 'Software Design and Architecture',    'core',    prog_bsse, dept_cs,  ['GA-SE-3']),
            ('SE4', 'SWE311', 'Software Testing and Quality',        'core',    prog_bsse, dept_cs,  ['GA-SE-1', 'GA-SE-3']),
            ('SE5', 'SWE321', 'Software Project Management',         'core',    prog_bsse, dept_cs,  ['GA-SE-4', 'GA-SE-5']),
            ('SE6', 'SWE411', 'Agile and DevOps Practices',          'elective',prog_bsse, dept_cs,  ['GA-SE-4', 'GA-SE-5']),
            ('SE7', 'SWE421', 'Capstone Project',                    'core',    prog_bsse, dept_cs,  ['GA-SE-3', 'GA-SE-4', 'GA-SE-6']),
            ('B1',  'BBA101', 'Principles of Management',            'core',    prog_bba,  dept_biz, ['GA-B1', 'GA-B4']),
            ('B2',  'BBA201', 'Financial Accounting',                'core',    prog_bba,  dept_biz, ['GA-B1', 'GA-B2']),
            ('B3',  'BBA211', 'Marketing Management',                'core',    prog_bba,  dept_biz, ['GA-B1', 'GA-B3']),
            ('B4',  'BBA301', 'Business Ethics and Law',             'core',    prog_bba,  dept_biz, ['GA-B5']),
            ('B5',  'BBA311', 'Entrepreneurship',                    'elective',prog_bba,  dept_biz, ['GA-B6', 'GA-B2']),
            ('B6',  'BBA401', 'Strategic Management',                'core',    prog_bba,  dept_biz, ['GA-B2', 'GA-B4']),
            ('M1',  'MBA501', 'Corporate Strategy',                  'core',    prog_mba,  dept_biz, ['GA-M1', 'GA-M2']),
            ('M2',  'MBA511', 'International Business',              'core',    prog_mba,  dept_biz, ['GA-M3']),
            ('M3',  'MBA521', 'Leadership and Organisational Behaviour','core', prog_mba,  dept_biz, ['GA-M4', 'GA-M1']),
            ('M4',  'MBA531', 'Advanced Financial Management',       'core',    prog_mba,  dept_biz, ['GA-M2']),
            ('M5',  'MBA601', 'MBA Thesis',                          'core',    prog_mba,  dept_biz, ['GA-M1', 'GA-M3', 'GA-M4']),
        ]
        for slug, code, title, ctype, program, dept, ga_ids in course_data:
            course, _ = Course.objects.get_or_create(
                slug=slug,
                defaults=dict(code=code, title=title, type=ctype, program=program, department=dept, credit_hours=3)
            )
            course.mapped_gas.set([all_gas[g] for g in ga_ids if g in all_gas])
        self.stdout.write('  ✓ Courses')

        # Users
        qa_user_cs, _ = User.objects.get_or_create(username='qa_computing', defaults=dict(
            email='qa.computing@iqra.edu.pk', first_name='Sara', last_name='Khan',
            role='qa', password=make_password('qapass123'), is_active=True))
        QAProfile.objects.get_or_create(user=qa_user_cs, defaults=dict(department=dept_cs, employee_id='QA-CS-001'))

        qa_user_biz, _ = User.objects.get_or_create(username='qa_business', defaults=dict(
            email='qa.business@iqra.edu.pk', first_name='Nadia', last_name='Ahmed',
            role='qa', password=make_password('qapass123'), is_active=True))
        QAProfile.objects.get_or_create(user=qa_user_biz, defaults=dict(department=dept_biz, employee_id='QA-BIZ-001'))

        for username, first, last, email, dept, emp_id, designation in [
            ('dr_ali',    'Dr. Ali',    'Hassan', 'ali.hassan@iqra.edu.pk',   dept_cs,  'INS-CS-001',  'Associate Professor'),
            ('dr_fatima', 'Dr. Fatima', 'Malik',  'fatima.malik@iqra.edu.pk', dept_cs,  'INS-CS-002',  'Assistant Professor'),
            ('dr_usman',  'Dr. Usman',  'Sheikh', 'usman.sheikh@iqra.edu.pk', dept_biz, 'INS-BIZ-001', 'Senior Lecturer'),
        ]:
            u, _ = User.objects.get_or_create(username=username, defaults=dict(
                email=email, first_name=first, last_name=last,
                role='instructor', password=make_password('instpass123'), is_active=True))
            InstructorProfile.objects.get_or_create(user=u, defaults=dict(department=dept, employee_id=emp_id, designation=designation))

        for username, first, last, email, prog, roll, batch in [
            ('ahmed_cs',  'Ahmed', 'Raza',     'ahmed.raza@student.iqra.edu.pk',    prog_bscs, 'FA22-BSCS-0012', 2022),
            ('zara_cs',   'Zara',  'Siddiqui', 'zara.siddiqui@student.iqra.edu.pk', prog_bscs, 'FA22-BSCS-0045', 2022),
            ('hamza_se',  'Hamza', 'Tariq',    'hamza.tariq@student.iqra.edu.pk',   prog_bsse, 'FA22-BSSE-0001', 2022),
            ('aisha_bba', 'Aisha', 'Nawaz',    'aisha.nawaz@student.iqra.edu.pk',   prog_bba,  'FA22-BBA-0001',  2022),
        ]:
            u, _ = User.objects.get_or_create(username=username, defaults=dict(
                email=email, first_name=first, last_name=last,
                role='student', password=make_password('stupass123'), is_active=True))
            Student.objects.get_or_create(user=u, defaults=dict(program=prog, roll_number=roll, batch_year=batch))

        self.stdout.write('  ✓ Users')

        # Instructor demo courses
        dr_ali = InstructorProfile.objects.get(user__username='dr_ali')
        InstructorCourse.objects.create(
            instructor=dr_ali, frontend_id='course-demo-1',
            code='CMC371', title='Software Engineering',
            department=dept_cs, program=prog_bscs, credit_hours=3,
            categories=[
                {"name":"Assignments","percentage":15,"units":3},
                {"name":"Quizzes","percentage":10,"units":3},
                {"name":"Class Participation","percentage":5,"units":1},
                {"name":"Class Project","percentage":15,"units":1},
                {"name":"Presentation","percentage":5,"units":1},
                {"name":"Mid Term","percentage":20,"units":1},
                {"name":"Final","percentage":30,"units":1},
            ],
            units_data={
                "Assignments":[{"unitNo":1,"passing":5,"totalMarks":10,"weightage":33.3},{"unitNo":2,"passing":5,"totalMarks":10,"weightage":33.3},{"unitNo":3,"passing":5,"totalMarks":10,"weightage":33.4}],
                "Quizzes":[{"unitNo":1,"passing":5,"totalMarks":10,"weightage":33.3},{"unitNo":2,"passing":5,"totalMarks":10,"weightage":33.3},{"unitNo":3,"passing":5,"totalMarks":10,"weightage":33.4}],
                "Class Participation":[{"unitNo":1,"passing":5,"totalMarks":10,"weightage":100}],
                "Class Project":[{"unitNo":1,"passing":15,"totalMarks":30,"weightage":100}],
                "Presentation":[{"unitNo":1,"passing":5,"totalMarks":10,"weightage":100}],
                "Mid Term":[{"unitNo":1,"passing":15,"totalMarks":30,"weightage":100}],
                "Final":[{"unitNo":1,"passing":20,"totalMarks":40,"weightage":100}],
            },
            students=[
                {"regNo":"FA22-BSCS-0012","name":"Abdur Rehman Khalid","marks":{"Assignments-1":8.5,"Assignments-2":9.0,"Assignments-3":7.5,"Quizzes-1":7.0,"Quizzes-2":8.5,"Quizzes-3":9.0,"Class Participation-1":9.0,"Class Project-1":26.5,"Presentation-1":8.0,"Mid Term-1":24.5,"Final-1":34.0}},
                {"regNo":"FA22-BSCS-0045","name":"Syeda Fatima Alvi","marks":{"Assignments-1":9.0,"Assignments-2":8.0,"Assignments-3":8.5,"Quizzes-1":8.0,"Quizzes-2":7.5,"Quizzes-3":6.5,"Class Participation-1":8.0,"Class Project-1":25.0,"Presentation-1":9.0,"Mid Term-1":22.0,"Final-1":32.5}},
            ],
            obe_questions=[],
            obe_marks={},
        )
        self.stdout.write('  ✓ Demo Instructor Courses')

        self.stdout.write(self.style.SUCCESS('\n✅  Seed complete!'))
        self.stdout.write(f'   Departments : {Department.objects.count()}')
        self.stdout.write(f'   Programs    : {Program.objects.count()}')
        self.stdout.write(f'   GAs         : {GraduateAttribute.objects.count()}')
        self.stdout.write(f'   Courses     : {Course.objects.count()}')
        self.stdout.write(f'   Users       : {User.objects.count()}')
        self.stdout.write('\n  Credentials:')
        self.stdout.write('   qa_computing / qapass123')
        self.stdout.write('   qa_business  / qapass123')
        self.stdout.write('   dr_ali       / instpass123')
        self.stdout.write('   ahmed_cs     / stupass123')
