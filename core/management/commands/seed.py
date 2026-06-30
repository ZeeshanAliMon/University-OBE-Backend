from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from core.models import (
    User, Department, Program, ProgramObjective, POGAMapping,
    GraduateAttribute, CLO, QAProfile, InstructorProfile, Student,
    Course, InstructorCourse, GradeScale, MarksCategory, UnitItem,
    OBEQuestion, CourseStudent, StudentMark, OBEStudentMark,
    AdmissionStudent, DeptAdminProfile, AdmissionProfile, CourseAssignment,
    SemesterPlan, FinalResult,
)


class Command(BaseCommand):
    help = 'Seed the database with real Iqra University OBE data'

    def handle(self, *args, **kwargs):
        self.stdout.write('🌱  Seeding database ...')

        # ── Clean slate ───────────────────────────────────────────────────────
        for model in [
            FinalResult,
            OBEStudentMark, StudentMark, CourseStudent, OBEQuestion, CLO,
            UnitItem, MarksCategory, GradeScale, InstructorCourse,
            POGAMapping, ProgramObjective, Course, GraduateAttribute,
            AdmissionStudent, Student,
            CourseAssignment, InstructorProfile, QAProfile,
            DeptAdminProfile, AdmissionProfile,
            SemesterPlan,
            Program, Department,
        ]:
            model.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        # Keep superuser but recreate if missing
        if not User.objects.filter(is_superuser=True).exists():
            User.objects.create_superuser(
                username='zeeshan', email='zeeshan@iqra.edu.pk', password='zeeshan'
            )
        self.stdout.write('  ✓ Cleared old data')

        # ── Departments ───────────────────────────────────────────────────────
        depts = {}
        dept_data = [
            ('computing', 'Department of Computing and Technology',
             'To emerge as a global leader in computer science research and education by driving technological innovation, solving real-world challenges, and empowering future leaders.',
             'To foster academic excellence and cutting-edge research, positioning our department as a global leader in computer science innovation. By instilling ethical values, technical prowess, and interdisciplinary knowledge, we prepare students for impactful careers in the field.'),
            ('business', 'Department of Business Administration',
             'To be a leading business school recognized globally for nurturing entrepreneurial mindsets and ethical leadership in the corporate world.',
             'To empower students with innovative business education, pioneering research capabilities, and ethical principles designed to create future business leaders.'),
            ('engineering', 'Department of Engineering and Applied Sciences',
             'To foster innovation, sustainable development, and global leadership in physical, chemical, and electrical systems development.',
             'To cultivate engineering leaders through rigorous experiential learning, research excellence, and socially responsible designs.'),
            ('media', 'Department of Media and Communications',
             'To inspire creative thinking, truth seeking, and advanced media production standards for modern media landscapes.',
             'To prepare future journalists and digital marketers with robust storytelling, visual art principles, and ethical reporting practices.'),
            ('health', 'Department of Health and Life Sciences',
             'To be a center of clinical excellence and biotechnology research that transforms human health and well-being.',
             'To empower practitioners and researchers through state-of-the-art clinical skills, bioethics education, and dynamic scientific inquiry.'),
        ]
        for slug, name, vision, mission in dept_data:
            depts[slug] = Department.objects.create(
                dept_id=slug, name=name, vision=vision, mission=mission
            )
        self.stdout.write('  ✓ Departments (5)')

        # ── Programs ──────────────────────────────────────────────────────────
        progs = {}
        prog_data = [
            # Computing
            ('bscs',   'Bachelor of Science in Computer Science',              'BSCS',   'computing'),
            ('bsse',   'Bachelor of Science in Software Engineering',          'BSSE',   'computing'),
            ('bsai',   'Bachelor of Science in Artificial Intelligence',       'BSAI',   'computing'),
            ('bscy',   'Bachelor of Science in Cyber Security',                'BSCY',   'computing'),
            # Business
            ('bba',    'Bachelor of Business Administration',                  'BBA',    'business'),
            ('bsaf',   'Bachelor of Science in Accounting and Finance',        'BSAF',   'business'),
            ('mba',    'Master of Business Administration',                    'MBA',    'business'),
            # Engineering
            ('be_ee',  'Bachelor of Engineering in Electrical Engineering',    'BE-EE',  'engineering'),
            ('be_ce',  'Bachelor of Engineering in Computer Engineering',      'BE-CE',  'engineering'),
            ('be_civ', 'Bachelor of Engineering in Civil Engineering',         'BE-CIV', 'engineering'),
            # Media
            ('bs_ms',  'Bachelor of Science in Media Studies',                 'BSMS',   'media'),
            ('bs_dm',  'Bachelor of Science in Digital Marketing',             'BSDM',   'media'),
            ('ms_jr',  'Master of Science in Journalism',                      'MSJR',   'media'),
            # Health
            ('dpt',    'Doctor of Physical Therapy',                           'DPT',    'health'),
            ('bs_n',   'Bachelor of Science in Nursing',                       'BSN',    'health'),
            ('bs_bt',  'Bachelor of Science in Biotechnology',                 'BSBT',   'health'),
        ]
        for slug, name, code, dept_slug in prog_data:
            progs[slug] = Program.objects.create(
                name=name, code=code,
                department=depts[dept_slug]
            )
        self.stdout.write('  ✓ Programs (16)')

        # ── Graduate Attributes ───────────────────────────────────────────────
        all_gas = {}
        ga_data = [
            # Computing (10)
            ('GA-1',  'Academic Education',                    'Completion of an accredited program of study designed to prepare graduates as computing professionals.',        'computing'),
            ('GA-2',  'Knowledge for Solving Computing Problems','Apply knowledge of computing fundamentals, mathematics, science, and domain knowledge to computing models.',   'computing'),
            ('GA-3',  'Problem Analysis',                      'Identify and solve complex computing problems using fundamental principles of mathematics and computing sciences.','computing'),
            ('GA-4',  'Design/Development of Solutions',       'Design and evaluate solutions for complex computing problems and systems that meet specified needs.',             'computing'),
            ('GA-5',  'Modern Tool Usage',                     'Create, select, or adapt and apply appropriate techniques, resources, and modern computing tools.',              'computing'),
            ('GA-6',  'Individual and Team Work',              'Function effectively as an individual and as a member or leader of a team in multidisciplinary settings.',       'computing'),
            ('GA-7',  'Communication',                         'Communicate effectively with the computing community about complex computing activities.',                       'computing'),
            ('GA-8',  'Computing Professionalism and Society', 'Understand and assess societal, health, safety, legal, and cultural issues within local and global contexts.',   'computing'),
            ('GA-9',  'Ethics',                                'Understand and commit to professional ethics, responsibilities, and norms of professional computing practice.',  'computing'),
            ('GA-10', 'Life-long Learning',                    'Recognize the need and ability to engage in independent learning for continual development.',                    'computing'),
            # Business (8)
            ('GA-B1', 'Business Analytics & Decision Making',  'Execute comprehensive business analysis and apply quantitative tools for strategic decision support.',           'business'),
            ('GA-B2', 'Leadership & Teamwork',                 'Foster strong collaborative performance, conflict resolution, and motivational team frameworks.',                'business'),
            ('GA-B3', 'Strategic Thinking',                    'Synthesize market trends, competitive intelligence, and internal structures to deploy agile business vision.',   'business'),
            ('GA-B4', 'Financial Literacy',                    'Evaluate balance sheets, corporate portfolios, and financial statements to drive corporate value addition.',     'business'),
            ('GA-B5', 'Corporate Social Responsibility & Ethics','Demonstrate deep compliance, corporate transparency, and standard professional ethics.',                      'business'),
            ('GA-B6', 'Communication & Presenting',            'Deliver highly structured business communications, elevator pitches, and expert corporate reporting.',           'business'),
            ('GA-B7', 'Critical Advisory',                     'Troubleshoot complex business cases and offer sustainable, optimized pathways to enterprise models.',            'business'),
            ('GA-B8', 'Business Enterprise',                   'Exhibit high entrepreneurial alertness, business opportunity detection traits, and adaptive startup frameworks.','business'),
            # Engineering (4)
            ('GA-E1', 'Engineering Knowledge',                 'Apply mathematics, science, and engineering fundamentals to complex engineering problems.',                      'engineering'),
            ('GA-E2', 'Design & Investigation',                'Formulate system parameters and conduct valid experiment designs for engineering problems.',                     'engineering'),
            ('GA-E3', 'Modern Engineering Tools',              'Deploy state-of-the-art computational simulation and engineering design tools.',                                 'engineering'),
            ('GA-E4', 'Ethics & Environment',                  'Mitigate ecological hazards and adhere to professional codes in engineering practice.',                         'engineering'),
            # Media (4)
            ('GA-M1', 'Media Literacy',                        'Analyze structural paradigms in mass communication streams and digital media.',                                 'media'),
            ('GA-M2', 'Content Strategy',                      'Optimize user attention dynamics and narrative engagement loops for digital audiences.',                         'media'),
            ('GA-M3', 'Digital Tools Production',              'Design premium multimedia vectors and software configurations for media production.',                            'media'),
            ('GA-M4', 'Acoustic & Media Ethics',               'Defend journalism integrity standards and ethical reporting practices.',                                         'media'),
            # Health (4)
            ('GA-H1', 'Medical Knowledge',                     'Demonstrate rigorous understanding of biological mechanics and clinical sciences.',                             'health'),
            ('GA-H2', 'Clinical Excellence',                   'Perform diagnostic inquiries and execute treatment designs safely and effectively.',                             'health'),
            ('GA-H3', 'Scientific Research',                   'Formulate bio-informatics queries and test chemical hypotheses through rigorous research.',                      'health'),
            ('GA-H4', 'Bioethics & Patient Advocacy',          'Enforce patient rights and medical ethics codes in clinical and research settings.',                            'health'),
        ]
        for ga_id, name, desc, dept_slug in ga_data:
            all_gas[ga_id] = GraduateAttribute.objects.create(
                ga_id=ga_id, name=name, description=desc,
                department=depts[dept_slug]
            )
        self.stdout.write('  ✓ Graduate Attributes (30)')

        # ── Program Objectives ────────────────────────────────────────────────
        po_data = {
            'bscs':   [
                ('PO1', 'Establishing in-depth understanding of theoretical concepts related to computer science.', ['GA-1','GA-2']),
                ('PO2', 'Applying core Computer Science knowledge and analytical skills to optimally solve real-world problems.', ['GA-1','GA-2','GA-3','GA-4','GA-5']),
                ('PO3', 'Imbuing quest for learning and engaging in continuous professional development in the field of computer science.', ['GA-3','GA-4','GA-6','GA-7','GA-8','GA-10']),
                ('PO4', 'Developing the ability to work in a multi-disciplinary and multi cultural environment in teams incorporating soft skills and maintaining high ethical standards.', ['GA-6','GA-7','GA-9']),
            ],
            'bsse':   [
                ('PO1', 'Mastery of software design patterns and system architecture specifications.', ['GA-1','GA-4']),
                ('PO2', 'Applying software engineering lifecycles and modern testing frameworks to construct robust products.', ['GA-2','GA-4','GA-5']),
                ('PO3', 'Understanding of professional and ethical responsibilities in software development.', ['GA-8','GA-9']),
                ('PO4', 'Engaging in lifelong learning to adapt to emerging software frameworks and AI-assisted development tools.', ['GA-10']),
            ],
            'bscy':   [
                ('PO1', 'Analyzing security properties and identifying vulnerabilities in networks and cloud architectures.', ['GA-3','GA-4']),
                ('PO2', 'Implementing high-fidelity cryptographic models and access control measures.', ['GA-2','GA-5']),
                ('PO3', 'Formulating disaster recovery protocols and ethical hacking methodologies.', ['GA-8','GA-9']),
                ('PO4', 'Communicating risk profiles and policy compliance metrics effectively with executive stakeholders.', ['GA-7']),
            ],
            'bsai':   [
                ('PO1', 'Apply mathematical and computational foundations to AI problem formulation and solution.', ['GA-1','GA-2']),
                ('PO2', 'Design and implement intelligent systems using modern ML, DL, and NLP frameworks.', ['GA-3','GA-4','GA-5']),
                ('PO3', 'Evaluate AI solutions for societal impact, fairness, and ethical implications.', ['GA-8','GA-9']),
                ('PO4', 'Engage in research-oriented lifelong learning in the evolving field of artificial intelligence.', ['GA-7','GA-10']),
            ],
            'bba':    [
                ('PO1', 'Mastering Core Business Management Skills and Analytical Tools.', ['GA-B1','GA-B4']),
                ('PO2', 'Strategic planning, operations synthesis, and ethical decision modeling.', ['GA-B2','GA-B3','GA-B5']),
                ('PO3', 'Fostering innovative business development strategies and executive communication.', ['GA-B3','GA-B6','GA-B8']),
                ('PO4', 'Developing adaptive management capabilities in multi-dimensional market climates.', ['GA-B2','GA-B7']),
            ],
            'bsaf':   [
                ('PO1', 'Applying advanced taxation and compliance mechanisms in financial reporting.', ['GA-B1','GA-B4']),
                ('PO2', 'Executing rigorous quantitative audit procedures and risk assessments.', ['GA-B4','GA-B7']),
                ('PO3', 'Synthesizing investment strategies and portfolio management structures.', ['GA-B3','GA-B8']),
                ('PO4', 'Engaging ethical leadership guidelines in corporate accounting structures.', ['GA-B2','GA-B5']),
            ],
            'mba':    [
                ('PO1', 'Formulating high-level global market expansion strategies and supply chain management.', ['GA-B3','GA-B8']),
                ('PO2', 'Driving executive data-driven decision optimization via business intelligence frameworks.', ['GA-B1','GA-B7']),
                ('PO3', 'Negotiating complex stakeholder values with impeccable corporate communication.', ['GA-B2','GA-B6']),
                ('PO4', 'Championing systemic corporate social responsibility initiatives.', ['GA-B5']),
            ],
            'be_ee':  [
                ('PO1', 'Designing electrical power systems and modern grid architectures.', ['GA-E1','GA-E2']),
                ('PO2', 'Applying signal processing mechanisms and embedded controls.', ['GA-E2','GA-E3']),
                ('PO3', 'Evaluating safety protocols and environmental impact of power setups.', ['GA-E4']),
                ('PO4', 'Communicating engineering designs effectively across technical teams.', ['GA-E2','GA-E3']),
            ],
            'be_ce':  [
                ('PO1', 'Designing digital circuits and VLSI architectures for computational systems.', ['GA-E1','GA-E2']),
                ('PO2', 'Deploying embedded systems and IoT protocols for real-time applications.', ['GA-E2','GA-E3']),
                ('PO3', 'Assessing cybersecurity risks in hardware and firmware architectures.', ['GA-E3','GA-E4']),
                ('PO4', 'Collaborating ethically within multidisciplinary engineering project teams.', ['GA-E4']),
            ],
            'be_civ': [
                ('PO1', 'Applying structural and geotechnical engineering principles to infrastructure.', ['GA-E1','GA-E2']),
                ('PO2', 'Designing environmentally sustainable civil engineering solutions.', ['GA-E2','GA-E4']),
                ('PO3', 'Managing complex construction projects with professional integrity.', ['GA-E3','GA-E4']),
                ('PO4', 'Evaluating safety and regulatory compliance in civil engineering practice.', ['GA-E4']),
            ],
            'bs_ms':  [
                ('PO1', 'Comprehending historical theories of media consumption and social discourse.', ['GA-M1']),
                ('PO2', 'Mastering advanced film production, screenwriting, and cinematic lighting.', ['GA-M2','GA-M3']),
                ('PO3', 'Critically analyzing television formats and broadcast guidelines.', ['GA-M1','GA-M4']),
                ('PO4', 'Managing multi-cam productions and digital media editing workflows.', ['GA-M3']),
            ],
            'bs_dm':  [
                ('PO1', 'Designing data-driven digital marketing campaigns across omnichannel platforms.', ['GA-M2','GA-M3']),
                ('PO2', 'Applying SEO, SEM, and social media analytics to optimize brand visibility.', ['GA-M1','GA-M2']),
                ('PO3', 'Crafting persuasive digital narratives compliant with ethical advertising.', ['GA-M4']),
                ('PO4', 'Measuring campaign ROI using digital intelligence dashboards.', ['GA-M2','GA-M3']),
            ],
            'ms_jr':  [
                ('PO1', 'Investigating and reporting complex socio-political stories with factual rigor.', ['GA-M1','GA-M4']),
                ('PO2', 'Producing broadcast-quality multimedia reports for global news networks.', ['GA-M2','GA-M3']),
                ('PO3', 'Applying data journalism methods to uncover systemic issues.', ['GA-M1','GA-M2']),
                ('PO4', 'Upholding ethical journalism standards under high-pressure editorial conditions.', ['GA-M4']),
            ],
            'dpt':    [
                ('PO1', 'Applying evidence-based physiotherapy assessments to musculoskeletal conditions.', ['GA-H1','GA-H2']),
                ('PO2', 'Designing individualized rehabilitation protocols for neurological impairments.', ['GA-H2','GA-H3']),
                ('PO3', 'Integrating bioethics and patient-centered communication in clinical practice.', ['GA-H4']),
                ('PO4', 'Conducting systematic clinical research to advance physical therapy practice.', ['GA-H3']),
            ],
            'bs_n':   [
                ('PO1', 'Delivering safe, evidence-based nursing care across diverse patient populations.', ['GA-H1','GA-H2']),
                ('PO2', 'Applying pharmacological and clinical knowledge in acute and primary care settings.', ['GA-H1','GA-H2']),
                ('PO3', 'Advocating for patient rights and demonstrating ethical clinical decision-making.', ['GA-H4']),
                ('PO4', 'Contributing to healthcare quality improvement through nursing research.', ['GA-H3']),
            ],
            'bs_bt':  [
                ('PO1', 'Applying molecular biology and biochemistry principles to biotechnology research.', ['GA-H1','GA-H3']),
                ('PO2', 'Designing genetic engineering experiments using modern bioinformatics tools.', ['GA-H2','GA-H3']),
                ('PO3', 'Evaluating biosafety protocols and ethical standards in biotech research.', ['GA-H4']),
                ('PO4', 'Communicating research outcomes through scientific publications and presentations.', ['GA-H3']),
            ],
        }

        for prog_slug, pos in po_data.items():
            program = progs[prog_slug]
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

        # ── Courses ───────────────────────────────────────────────────────────
        cs_courses = [
            ('C1','CMC111','Programming Fundamentals','core',['GA-1','GA-2','GA-4']),
            ('C2','GER111','Application of Information & Communication Technologies','core',['GA-1','GA-2','GA-5']),
            ('C3','GER121','Functional English','core',['GA-1','GA-7']),
            ('C4','GER131','Calculus and Analytic Geometry','core',['GA-1','GA-2','GA-3']),
            ('C5','GER141','Islamic Studies','core',['GA-1','GA-6','GA-8','GA-9']),
            ('C6','GER151','Natural Science (Applied Physics)','core',['GA-1','GA-2']),
            ('C7','MTE111','Multivariable Calculus','core',['GA-1','GA-2','GA-3']),
            ('C8','CMC112','Object Oriented Programming','core',['GA-1','GA-2','GA-4']),
            ('C9','CMC121','Digital Logic Design','core',['GA-1','GA-2','GA-3']),
            ('C10','GER122','Expository Writing','core',['GA-1','GA-6','GA-7']),
            ('C11','GER132','Discrete Structures','core',['GA-1','GA-2','GA-3']),
            ('C12','GER142','Ideology and Constitution of Pakistan','core',['GA-1','GA-8','GA-9','GA-10']),
            ('C13','MTE212','Probability & Statistics','core',['GA-1','GA-2','GA-3']),
            ('C14','CMC222','Computer Organization & Assembly Language','core',['GA-1','GA-2','GA-3']),
            ('C15','CMC251','Data Structures','core',['GA-1','GA-2','GA-3','GA-5']),
            ('C16','CSC252','Theory of Automata','core',['GA-1','GA-2','GA-3','GA-4']),
            ('C17','CMC261','Computer Networks','core',['GA-1','GA-2','GA-3']),
            ('C18','MTE213','Linear Algebra','core',['GA-1','GA-2','GA-3']),
            ('C19','MTE221','Technical & Business Writing','core',['GA-1','GA-6','GA-8']),
            ('C20','CSC223','Computer Architecture','core',['GA-1','GA-2','GA-5']),
            ('C21','CMC241','Operating Systems','core',['GA-1','GA-2','GA-3']),
            ('C22','CMC253','Analysis of Algorithms','core',['GA-1','GA-2','GA-3','GA-4']),
            ('C23','GER261','Introduction to Management','core',['GA-1','GA-3','GA-6']),
            ('C24','CMC331','Database Systems','core',['GA-1','GA-2','GA-3','GA-5']),
            ('C25','CSC354','Compiler Construction','core',['GA-1','GA-2','GA-3','GA-4']),
            ('C26','CMC362','Information Security','core',['GA-1','GA-2','GA-3','GA-4']),
            ('C27','CMC371','Software Engineering','core',['GA-1','GA-2','GA-3']),
            ('C28','CSC332','Advance Database Management Systems','core',['GA-1','GA-2','GA-3','GA-5']),
            ('C29','CMC381','Artificial Intelligence','core',['GA-1','GA-2','GA-3','GA-4','GA-5']),
            ('C30','CSC382','HCI & Computer Graphics','core',['GA-1','GA-3','GA-4','GA-5']),
            ('C31','ESC311','Introduction to Marketing','core',['GA-1','GA-7','GA-8','GA-9']),
            ('C32','CSC442','Parallel & Distributed Computing','core',['GA-1','GA-2','GA-4','GA-5']),
            ('C33','GER462','Technopreneurship','core',['GA-1','GA-7','GA-9','GA-10']),
            ('C34','CMC491','Final Year Project - I','core',['GA-1']),
            ('C35','GER443','Civics and Community Engagement','core',['GA-1','GA-7','GA-8','GA-9']),
            ('C36','GER463','Professional Practices','core',['GA-1','GA-8','GA-9','GA-10']),
            ('C37','CMC492','Final Year Project - II','core',['GA-1','GA-2','GA-3','GA-4','GA-5','GA-6','GA-7','GA-8','GA-9','GA-10']),
            ('C38','CSC467','Internet of Things','elective',['GA-1','GA-2','GA-3','GA-4']),
            ('C39','CMC381-E','Artificial Intelligence (Elective)','elective',['GA-1','GA-2','GA-4','GA-5']),
            ('C40','CSC436','Data Warehousing & Data Mining','elective',['GA-1','GA-2','GA-3','GA-7','GA-10']),
            ('C41','CSC479','Machine Learning','elective',['GA-1','GA-2','GA-4','GA-5']),
            ('C42','CSC435','Mobile Application Development','elective',['GA-1','GA-2','GA-3']),
            ('C43','CSC321','Embedded Systems','elective',['GA-1','GA-2','GA-5']),
            ('C44','CSC478','Routing and Switching','elective',['GA-1','GA-2','GA-3','GA-4']),
        ]
        biz_courses = [
            ('CB1','BUS101','Principles of Management','core',['GA-B2','GA-B3','GA-B6']),
            ('CB2','MKT111','Principles of Marketing','core',['GA-B3','GA-B6','GA-B8']),
            ('CB3','ACC121','Financial Accounting','core',['GA-B1','GA-B4']),
            ('CB4','HRM211','Human Resource Management','core',['GA-B2','GA-B5','GA-B6']),
            ('CB5','ECO131','Microeconomics','core',['GA-B1','GA-B3']),
            ('CB6','MGT222','Organizational Behavior','core',['GA-B2','GA-B5','GA-B6']),
            ('CB7','FIN311','Business Finance','core',['GA-B1','GA-B4']),
            ('CB8','MGT331','Strategic Management','core',['GA-B3','GA-B5','GA-B7','GA-B8']),
            ('CB9','BUS491','BBA Capstone Project - I','core',['GA-B1','GA-B2','GA-B3','GA-B6']),
            ('CB10','BUS492','BBA Capstone Project - II','core',['GA-B1','GA-B2','GA-B3','GA-B4','GA-B5','GA-B6','GA-B7','GA-B8']),
            ('CB11','ENTR451','Social Entrepreneurship','elective',['GA-B5','GA-B8']),
            ('CB12','FIN462','Investment Portfolio Analysis','elective',['GA-B1','GA-B4','GA-B7']),
        ]

        for slug, code, title, ctype, ga_ids in cs_courses:
            c = Course.objects.create(code=code, title=title, type=ctype,
                                      program=progs['bscs'], department=depts['computing'], credit_hours=3)
            c.mapped_gas.set([all_gas[g] for g in ga_ids if g in all_gas])

        for slug, code, title, ctype, ga_ids in biz_courses:
            c = Course.objects.create(code=code, title=title, type=ctype,
                                      program=progs['bba'], department=depts['business'], credit_hours=3)
            c.mapped_gas.set([all_gas[g] for g in ga_ids if g in all_gas])

        # Mon test course — Health department
        mon_course = Course.objects.create(
            code='MON101', title='Mon Course', type='core',
            program=progs['bs_bt'], department=depts['health'], credit_hours=3
        )
        if 'GA-H1' in all_gas:
            mon_course.mapped_gas.set([all_gas['GA-H1']])

        self.stdout.write('  ✓ Courses (44 Computing + 12 Business + 1 Mon)')

        # ── Users ─────────────────────────────────────────────────────────────
        # QA Officers
        for username, first, last, email, dept_slug, emp_id in [
            ('qa_computing', 'Sara',  'Khan',  'qa.computing@iqra.edu.pk', 'computing', 'QA-CS-001'),
            ('qa_business',  'Nadia', 'Ahmed', 'qa.business@iqra.edu.pk',  'business',  'QA-BIZ-001'),
            ('qa_engineering','Zara', 'Malik', 'qa.eng@iqra.edu.pk',       'engineering','QA-ENG-001'),
        ]:
            u = User.objects.create(username=email, email=email,
                first_name=first, last_name=last,
                role='qa', password=make_password('qapass123'), is_active=True)
            QAProfile.objects.create(user=u, department=depts[dept_slug], employee_id=emp_id)

        # Admission Officer
        adm_user = User.objects.create(
            username='admission@iqra.edu.pk', email='admission@iqra.edu.pk',
            first_name='Admission', last_name='Officer',
            role='admission', password=make_password('admpass123'), is_active=True
        )
        AdmissionProfile.objects.create(
            user=adm_user, department=depts['computing'], employee_id='ADM-001'
        )

        # Zeeshan's admission account
        adm_zeeshan = User.objects.create(
            username='zeeshan@ali.com', email='zeeshan@ali.com',
            first_name='Zeeshan', last_name='Ali',
            role='admission', password=make_password('ijijijij'), is_active=True
        )
        AdmissionProfile.objects.create(
            user=adm_zeeshan, department=depts['computing'], employee_id='ADM-ZA-001'
        )

        # Mon admission account
        mon_adm = User.objects.create(
            username='mon@admission.com', email='mon@admission.com',
            first_name='Zeeshan', last_name='Admission',
            role='admission', password=make_password('ijijijij'), is_active=True
        )
        AdmissionProfile.objects.create(
            user=mon_adm, department=depts['health'], employee_id='ADM-MON-001'
        )

        # Department Admins
        for username, first, last, email, dept_slug, emp_id in [
            ('admin_computing',  'Ahmad',  'Raza',   'admin.computing@iqra.edu.pk',  'computing',   'DA-CS-001'),
            ('admin_business',   'Bilal',  'Tahir',  'admin.business@iqra.edu.pk',   'business',    'DA-BIZ-001'),
            ('admin_engineering','Hira',   'Baig',   'admin.engineering@iqra.edu.pk','engineering', 'DA-ENG-001'),
            ('zeeshan_dept',     'Zeeshan','Ali',    'ali@zeeshan.com',              'computing',   'DA-ZA-001'),

        ]:
            u = User.objects.create(username=email, email=email,
                first_name=first, last_name=last,
                role='dept_admin', password=make_password('adminpass123'), is_active=True)
            DeptAdminProfile.objects.create(user=u, department=depts[dept_slug], employee_id=emp_id)

        # Instructors
        instructor_profiles = {}
        for username, first, last, email, dept_slug, emp_id, designation in [
            ('dr_ali',    'Ali',    'Hassan', 'ali.hassan@iqra.edu.pk',   'computing',   'INS-CS-001', 'Associate Professor'),
            ('dr_fatima', 'Fatima', 'Malik',  'fatima.malik@iqra.edu.pk', 'computing',   'INS-CS-002', 'Assistant Professor'),
            ('dr_usman',  'Usman',  'Sheikh', 'usman.sheikh@iqra.edu.pk', 'business',    'INS-BIZ-001','Senior Lecturer'),
            ('dr_sara',   'Sara',   'Qadir',  'sara.qadir@iqra.edu.pk',   'engineering', 'INS-ENG-001','Lecturer'),
        ]:
            u = User.objects.create(username=email, email=email,
                first_name=first, last_name=last,
                role='instructor', password=make_password('instpass123'), is_active=True)
            p = InstructorProfile.objects.create(
                user=u, department=depts[dept_slug],
                employee_id=emp_id, designation=designation
            )
            instructor_profiles[username] = p

        # Mon dept admin (health) — password ijijijij
        mon_dadm = User.objects.create(
            username='mon@admin.com', email='mon@admin.com',
            first_name='Zeeshan', last_name='Admin',
            role='dept_admin', password=make_password('ijijijij'), is_active=True
        )
        DeptAdminProfile.objects.create(user=mon_dadm, department=depts['health'], employee_id='DA-MON-001')

        self.stdout.write('  ✓ Users (3 QA, 3 Dept Admins, 1 Admission, 4 Instructors)')

        # ── Admission Students ────────────────────────────────────────────────
        admission_data = [
            ('FA22-BSCS-0012', 'Abdur Rehman Khalid', 'computing', 'bscs', 'Fall',   '6th'),
            ('FA22-BSCS-0045', 'Syeda Fatima Alvi',   'computing', 'bscs', 'Fall',   '6th'),
            ('FA22-BSCS-0089', 'Zayan Ahmed Khan',    'computing', 'bscs', 'Fall',   '6th'),
            ('FA22-BSCS-0104', 'Misha Farooq',        'computing', 'bscs', 'Fall',   '6th'),
            ('FA23-BSSE-0011', 'Hamza Tariq',         'computing', 'bsse', 'Spring', '4th'),
            ('FA23-BSSE-0023', 'Iqra Bashir',         'computing', 'bsse', 'Spring', '4th'),
            ('FA22-BBA-0021',  'Bilal Hussain',       'business',  'bba',  'Spring', '6th'),
            ('FA22-BBA-0035',  'Amna Tariq',          'business',  'bba',  'Fall',   '6th'),
            ('FA23-BSAF-0008', 'Usman Raza',          'business',  'bsaf', 'Fall',   '4th'),
            ('FA24-BE-EE-001', 'Ahmed Khan',          'engineering','be_ee','Fall',   '2nd'),
            ('MON-BSBT-001',   'Zeeshan Student',     'health',    'bs_bt','Fall',   '1st'),
        ]
        for reg_no, name, dept_slug, prog_slug, batch, semester in admission_data:
            AdmissionStudent.objects.create(
                reg_no=reg_no, name=name,
                department=depts[dept_slug], program=progs[prog_slug],
                batch=batch, semester=semester
            )
        # Mon teacher (health) — password ijijijij
        mon_teacher_user = User.objects.create(
            username='mon@teacher.com', email='mon@teacher.com',
            first_name='Zeeshan', last_name='Teacher',
            role='instructor', password=make_password('ijijijij'), is_active=True
        )
        mon_teacher_profile = InstructorProfile.objects.create(
            user=mon_teacher_user, department=depts['health'],
            employee_id='INS-MON-001', designation='Lecturer'
        )

        self.stdout.write('  ✓ Admission Students (10)')

        # ── Demo Instructor Course ────────────────────────────────────────────
        dr_ali = instructor_profiles['dr_ali']
        ic = InstructorCourse.objects.create(
            instructor=dr_ali, frontend_id='course-demo-1',
            code='CMC371', title='Software Engineering', course_type='Theory',
            department=depts['computing'], program=progs['bscs'],
            credit_hours=3, clo_count=4, selected_grading_system='ready1',
        )
        for order, (grade, pct, pts) in enumerate([
            ('A',90,4.0),('A-',85,3.7),('B+',80,3.3),('B',75,3.0),
            ('B-',70,2.7),('C+',65,2.3),('C',60,2.0),('C-',55,1.7),
            ('D',50,1.0),('F',0,0.0),
        ]):
            GradeScale.objects.create(course=ic, grade=grade, min_percentage=pct, points=pts, order=order)

        categories_def = [
            ('Assignments',15,3,[(1,10,5,33.3,['CLO-1','CLO-2']),(2,10,5,33.3,['CLO-2','CLO-3']),(3,10,5,33.4,['CLO-1','CLO-3'])]),
            ('Quizzes',10,3,[(1,10,5,33.3,['CLO-1','CLO-2']),(2,10,5,33.3,['CLO-3','CLO-4']),(3,10,5,33.4,['CLO-1','CLO-4'])]),
            ('Class Participation',5,1,[(1,10,5,100,['CLO-1','CLO-2','CLO-3','CLO-4'])]),
            ('Class Project',15,1,[(1,30,15,100,['CLO-2','CLO-3','CLO-4'])]),
            ('Presentation',5,1,[(1,10,5,100,['CLO-1','CLO-2'])]),
            ('Lab Project',0,0,[]),('Problem Based Learning',0,0,[]),
            ('Complex Problem',0,0,[]),('Other Activities',0,0,[]),
            ('Viva',0,0,[]),('Lab Performance',0,0,[]),('Lab Reports',0,0,[]),
            ('Mid Term',20,1,[(1,30,15,100,['CLO-1','CLO-2','CLO-3'])]),
            ('Final',30,1,[(1,40,20,100,['CLO-1','CLO-2','CLO-3','CLO-4'])]),
        ]
        unit_map = {}
        for order, (cat_name, pct, units, unit_list) in enumerate(categories_def):
            cat = MarksCategory.objects.create(course=ic, name=cat_name, percentage=pct, units=units, order=order)
            for unit_no, total, passing, weightage, clos in unit_list:
                u = UnitItem.objects.create(category=cat, unit_no=unit_no,
                    total_marks=total, passing=passing, weightage=weightage, mapped_clos=clos)
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
                course=ic, frontend_id=fid, unit_item=unit_map.get((cat, uno)),
                category_name=cat, unit_no=uno, question_name=qname,
                max_marks=mm, mapped_clos=clos, order=ord_)

        for reg_no, name, marks, obe in [
            ('FA22-BSCS-0012','Abdur Rehman Khalid',
             {('Assignments',1):8.5,('Assignments',2):9.0,('Assignments',3):7.5,('Quizzes',1):7.0,
              ('Quizzes',2):8.5,('Quizzes',3):9.0,('Class Participation',1):9.0,
              ('Class Project',1):26.5,('Presentation',1):8.0,('Mid Term',1):24.5,('Final',1):34.0},
             {'q-demo-1':4.5,'q-demo-2':4.0,'q-demo-3':8.0,'q-demo-4':12.5,'q-demo-5':12.0}),
            ('FA22-BSCS-0045','Syeda Fatima Alvi',
             {('Assignments',1):9.0,('Assignments',2):8.0,('Assignments',3):8.5,('Quizzes',1):8.0,
              ('Quizzes',2):7.5,('Quizzes',3):6.5,('Class Participation',1):8.0,
              ('Class Project',1):25.0,('Presentation',1):9.0,('Mid Term',1):22.0,('Final',1):32.5},
             {'q-demo-1':5.0,'q-demo-2':3.5,'q-demo-3':7.5,'q-demo-4':11.0,'q-demo-5':11.0}),
            ('FA22-BSCS-0089','Zayan Ahmed Khan',
             {('Assignments',1):7.5,('Assignments',2):7.0,('Assignments',3):8.0,('Quizzes',1):6.0,
              ('Quizzes',2):5.0,('Quizzes',3):7.0,('Class Participation',1):7.0,
              ('Class Project',1):22.0,('Presentation',1):7.5,('Mid Term',1):19.5,('Final',1):28.0},
             {'q-demo-1':3.5,'q-demo-2':2.5,'q-demo-3':5.0,'q-demo-4':9.5,'q-demo-5':10.0}),
        ]:
            s = CourseStudent.objects.create(course=ic, reg_no=reg_no, name=name)
            for (cat, uno), score in marks.items():
                u = unit_map.get((cat, uno))
                if u:
                    StudentMark.objects.create(student=s, unit_item=u, score=score)
            for qid, score in obe.items():
                OBEStudentMark.objects.create(student=s, question=q_map[qid], score=score)



        # ── CLOs for demo course ──────────────────────────────────────────────
        ga_1 = all_gas.get('GA-1')
        ga_2 = all_gas.get('GA-2')
        ga_3 = all_gas.get('GA-3')
        ga_4 = all_gas.get('GA-4')
        clo_defs = [
            ('CLO-1', 'Explain fundamental software engineering concepts and lifecycle models.', ga_1, 1),
            ('CLO-2', 'Apply software design principles to produce modular and maintainable systems.', ga_2, 2),
            ('CLO-3', 'Analyse and decompose complex software problems using structured methodologies.', ga_3, 3),
            ('CLO-4', 'Evaluate software quality using testing strategies and review techniques.', ga_4, 4),
        ]
        for code, desc, ga, order in clo_defs:
            CLO.objects.create(
                course=ic, code=code, description=desc,
                mapped_ga=ga, order=order
            )
        self.stdout.write('  ✓ CLOs (4 CLOs mapped to GA-1 through GA-4)')

        self.stdout.write('  ✓ Demo Instructor Course + Marks')

        # ── Student Users (linked to AdmissionStudent reg_nos) ───────────────
        # These are login accounts for students whose directory entries
        # already exist in AdmissionStudent. reg_no must match exactly.
        student_logins = [
            ('ahmed_cs',  'Ahmed',  'Raza',     'ahmed.raza@student.iqra.edu.pk',    'FA22-BSCS-0012', progs['bscs'], depts['computing']),
            ('zara_cs',   'Zara',   'Siddiqui', 'zara.siddiqui@student.iqra.edu.pk', 'FA22-BSCS-0045', progs['bscs'], depts['computing']),
            ('hamza_se',  'Hamza',  'Tariq',    'hamza.tariq@student.iqra.edu.pk',   'FA22-BSSE-0011', progs['bsse'], depts['computing']),
            ('mon_student','Zeeshan','Student',  'mon@student.com',                    'MON-BSBT-001',   progs['bs_bt'],depts['health']),
        ]
        for username, first, last, email, reg_no, prog, dept in student_logins:
            u = User.objects.create(
                username=email, email=email,
                first_name=first, last_name=last,
                role='student', password=make_password('stupass123'), is_active=True
            )
            Student.objects.create(
                user=u, reg_no=reg_no,
                program=prog, department=dept
            )
        # Override mon student password to ijijijij
        try:
            mon_u = User.objects.get(email='mon@student.com')
            from django.contrib.auth.hashers import make_password as _mp
            mon_u.password = _mp('ijijijij')
            mon_u.save()
        except Exception:
            pass

        self.stdout.write('  ✓ Student Users (ahmed_cs, zara_cs, hamza_se → stupass123 | mon@student.com → ijijijij)')


        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS('\n✅  Seed complete!'))
        self.stdout.write(f'   Departments        : {Department.objects.count()}')
        self.stdout.write(f'   Programs           : {Program.objects.count()}')
        self.stdout.write(f'   Graduate Attributes: {GraduateAttribute.objects.count()}')
        self.stdout.write(f'   QA Courses         : {Course.objects.count()}')
        self.stdout.write(f'   Admission Students : {AdmissionStudent.objects.count()}')
        self.stdout.write(f'   Instructor Courses : {InstructorCourse.objects.count()}')
        self.stdout.write(f'   Users              : {User.objects.count()}')
        self.stdout.write('\n  Login credentials:')
        self.stdout.write('   qa.computing@iqra.edu.pk  / qapass123   → QA (Computing)')
        self.stdout.write('   qa.business@iqra.edu.pk   / qapass123   → QA (Business)')
        self.stdout.write('   qa.eng@iqra.edu.pk         / qapass123   → QA (Engineering)')
        self.stdout.write('   admission@iqra.edu.pk      / admpass123   → Admission Officer')
        self.stdout.write('   zeeshan@ali.com            / ijijijij     → Admission (Zeeshan)')
        self.stdout.write('   mon@admission.com          / ijijijij     → Admission (Mon)')
        self.stdout.write('   mon@admin.com              / ijijijij     → Dept Admin Health (Mon)')
        self.stdout.write('   mon@teacher.com            / ijijijij     → Instructor Health (Mon)')
        self.stdout.write('   mon@student.com            / ijijijij     → Student Health/Biotechnology (Mon)')
        self.stdout.write('   ali@zeeshan.com            / ijijijij     → Dept Admin (Computing)')
        self.stdout.write('   admin.computing@iqra.edu.pk/ adminpass123 → Dept Admin (Computing)')
        self.stdout.write('   ali.hassan@iqra.edu.pk     / instpass123  → Instructor')
        self.stdout.write('')
        self.stdout.write('  Superuser:')
        self.stdout.write('   zeeshan@iqra.edu.pk        / zeeshan      → Django Admin (/admin/)')
