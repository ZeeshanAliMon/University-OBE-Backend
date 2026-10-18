"""
Management command: setup_initial_data

Creates all base data needed for a fresh database:
  - Department (Computing and Technology)
  - Program (CS)
  - Default users (admin, teacher, student, dept_admin, qa, admission)
  - All 12 Washington Accord Graduate Attributes

Usage:
    python manage.py setup_initial_data
    python manage.py setup_initial_data --force   # re-run safely, skips existing
"""

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Setup all initial data for a fresh database'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Skip existing records instead of erroring')

    def handle(self, *args, **options):
        from core.models import Department, Program, User, GraduateAttribute

        self.stdout.write('\n=== OBE System Initial Setup ===\n')

        with transaction.atomic():

            # ── 1. Department ──────────────────────────────────────────────
            dept, created = Department.objects.get_or_create(
                dept_id='computing',
                defaults={
                    'name':    'Computing and Technology',
                    'vision':  'Excellence in computing education',
                    'mission': 'Produce skilled computing professionals',
                }
            )
            self.stdout.write(f'{"✓ Created" if created else "— Exists"} Department: {dept.name}')

            # ── 2. Program ─────────────────────────────────────────────────
            prog, created = Program.objects.get_or_create(
                code='CS',
                defaults={
                    'name':       'Computer Science (CS)',
                    'department': dept,
                    'vision':     'Excellence in CS education',
                    'mission':    'Produce skilled CS professionals',
                }
            )
            self.stdout.write(f'{"✓ Created" if created else "— Exists"} Program: {prog.name}')

            # ── 3. Users ───────────────────────────────────────────────────
            users = [
                dict(username='admin',     email='admin@obe.com',      password='admin123',    role='admin',      first='Admin',   last='User',  superuser=True),
                dict(username='teacher',   email='teacher@mon.com',     password='password123', role='instructor', first='Teacher', last='Ali',   superuser=False),
                dict(username='student',   email='student@mon.com',     password='password123', role='student',    first='Student', last='Ali',   superuser=False),
                dict(username='deptadmin', email='computing@mon.com',   password='password123', role='dept_admin', first='Dept',    last='Admin', superuser=False),
                dict(username='qa',        email='qa@mon.com',          password='password123', role='qa',         first='QA',      last='User',  superuser=False),
                dict(username='admission', email='admission@mon.com',   password='password123', role='admission',  first='Admission', last='User', superuser=False),
            ]

            self.stdout.write('\nUsers:')
            for u in users:
                if User.objects.filter(email=u['email']).exists():
                    self.stdout.write(f'  — Exists   {u["role"]:12} {u["email"]}')
                    continue
                if u['superuser']:
                    user = User.objects.create_superuser(
                        username=u['username'], email=u['email'],
                        password=u['password'], role=u['role'],
                        first_name=u['first'], last_name=u['last']
                    )
                else:
                    user = User.objects.create_user(
                        username=u['username'], email=u['email'],
                        password=u['password'], role=u['role'],
                        first_name=u['first'], last_name=u['last']
                    )
                self.stdout.write(f'  ✓ Created  {u["role"]:12} {u["email"]}  password: {u["password"]}')

            # ── 4. Graduate Attributes (Washington Accord 12 GAs) ──────────
            GAS = [
                (1,  'Engineering Knowledge',          'Apply knowledge of mathematics, science, engineering fundamentals and specialisation to complex engineering problems.'),
                (2,  'Problem Analysis',               'Identify, formulate, research and analyse complex engineering problems reaching substantiated conclusions.'),
                (3,  'Design/Development of Solutions','Design solutions for complex engineering problems that meet specified needs with consideration for safety and environment.'),
                (4,  'Investigation',                  'Conduct investigations of complex problems using research-based knowledge including design of experiments and data analysis.'),
                (5,  'Modern Tool Usage',              'Create, select and apply appropriate techniques, resources and modern engineering and IT tools to complex activities.'),
                (6,  'The Engineer and Society',       'Apply reasoning to assess societal, health, safety, legal and cultural issues relevant to professional engineering practice.'),
                (7,  'Environment and Sustainability', 'Understand and evaluate the sustainability and impact of engineering work in societal and environmental contexts.'),
                (8,  'Ethics',                         'Apply ethical principles and commit to professional ethics and responsibilities and norms of engineering practice.'),
                (9,  'Individual and Team Work',       'Function effectively as an individual, and as a member or leader in diverse teams and multidisciplinary settings.'),
                (10, 'Communication',                  'Communicate effectively on complex engineering activities with the engineering community and society at large.'),
                (11, 'Project Management',             'Demonstrate knowledge of engineering and management principles and apply these to manage projects in multidisciplinary environments.'),
                (12, 'Lifelong Learning',              'Recognise the need for and ability to engage in independent and life-long learning in the broadest context of technological change.'),
            ]

            self.stdout.write('\nGraduate Attributes (CS program):')
            created_count = 0
            for num, name, desc in GAS:
                ga_id = f'CS{num}'
                ga, created = GraduateAttribute.objects.get_or_create(
                    ga_id=ga_id,
                    defaults={'name': name, 'description': desc, 'department': dept, 'program': prog}
                )
                if created:
                    created_count += 1
                    self.stdout.write(f'  ✓ {ga_id}: {name}')
                else:
                    self.stdout.write(f'  — {ga_id}: {name} (exists)')

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Setup complete! {created_count} GAs created.\n'
            f'\nLogin credentials:\n'
            f'  Admin:      admin@obe.com       / admin123\n'
            f'  Teacher:    teacher@mon.com     / password123\n'
            f'  Student:    student@mon.com     / password123\n'
            f'  DeptAdmin:  computing@mon.com   / password123\n'
            f'  QA:         qa@mon.com          / password123\n'
            f'  Admission:  admission@mon.com   / password123\n'
        ))
