from django.core.management.base import BaseCommand
from core.models import (
    User, Department, Program, ProgramObjective,
    GraduateAttribute, POGAMapping
)


class Command(BaseCommand):
    help = 'Seed the database with initial data'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding database...')

        # ── Graduate Attributes ──────────────────────────────────────────────
        gas_data = [
            ('GA-1',  'Academic Education',
             'Completion of an accredited program of study designed to prepare graduates as computing professionals.'),
            ('GA-2',  'Knowledge for Solving Computing Problems',
             'Apply knowledge of computing fundamentals, knowledge of a computing specialization, and mathematics, science, and domain knowledge appropriate for the computing specialization to the abstraction and conceptualization of computing models from defined problems and requirements.'),
            ('GA-3',  'Problem Analysis',
             'Identify and solve complex computing problems reaching substantiated conclusions using fundamental principles of mathematics, computing sciences, and relevant domain disciplines.'),
            ('GA-4',  'Design/Development of Solutions',
             'Design and evaluate solutions for complex computing problems, and design and evaluate systems, components, or processes that meet specified needs.'),
            ('GA-5',  'Modern Tool Usage',
             'Create, select, or adapt and then apply appropriate techniques, resources, and modern computing tools to complex computing activities, with an understanding of the limitations.'),
            ('GA-6',  'Individual and Teamwork',
             'Function effectively as an individual and as a member or leader of a team in multidisciplinary settings.'),
            ('GA-7',  'Communication',
             'Communicate effectively with the computing community about complex computing activities by being able to comprehend and write effective reports, design documentation, make effective presentations, and give and understand clear instructions.'),
            ('GA-8',  'Computing Professionalism and Society',
             'Understand and assess societal, health, safety, legal, and cultural issues within local and global contexts, and the consequential responsibilities relevant to professional computing practice.'),
            ('GA-9',  'Ethics',
             'Understand and commit to professional ethics, responsibilities, and norms of professional computing practice.'),
            ('GA-10', 'Life-long Learning',
             'Recognize the need, and have the ability, to engage in independent learning for continual development as a computing professional.'),
        ]

        gas = {}
        for code, name, desc in gas_data:
            ga, created = GraduateAttribute.objects.get_or_create(
                code=code,
                defaults={'name': name, 'description': desc}
            )
            gas[code] = ga
            self.stdout.write(f'  {"Created" if created else "Exists "} GA: {code} - {name}')

        # ── Departments ──────────────────────────────────────────────────────
        departments_data = [
            {
                'code':    '1',
                'name':    'Computing and Technology',
                'vision':  'We are good person',
                'mission': 'I am a good person',
            },
            {
                'code':    '2',
                'name':    'BBA',
                'vision':  'Good bba',
                'mission': 'Bad bba',
            },
            {
                'code':    '3',
                'name':    'Nursing',
                'vision':  'this is nusing  vision',
                'mission': 'this is nusing  Mission',
            },
        ]

        departments = {}
        for d in departments_data:
            dept, created = Department.objects.get_or_create(
                code=d['code'],
                defaults={
                    'name':    d['name'],
                    'vision':  d['vision'],
                    'mission': d['mission'],
                }
            )
            departments[d['code']] = dept
            self.stdout.write(f'  {"Created" if created else "Exists "} Department: {d["name"]}')

        # ── Programs ─────────────────────────────────────────────────────────
        programs_data = [
            {'code': 'CT1', 'name': 'Computer Science',    'dept': '1'},
            {'code': 'CT2', 'name': 'Artificial Intelligence', 'dept': '1'},
            {'code': 'BB1', 'name': 'Financial',           'dept': '2'},
            {'code': '11',  'name': 'DCCN',                'dept': '1'},
            {'code': '12',  'name': 'Microbio',            'dept': '3'},
            {'code': '13',  'name': 'economics,',          'dept': '2'},
        ]

        programs = {}
        for p in programs_data:
            prog, created = Program.objects.get_or_create(
                code=p['code'],
                defaults={
                    'name':       p['name'],
                    'department': departments[p['dept']],
                }
            )
            programs[p['code']] = prog
            self.stdout.write(f'  {"Created" if created else "Exists "} Program: {p["name"]}')

        # ── Program Objectives for Computer Science (CT1) ────────────────────
        ct1 = programs['CT1']
        pos_data = [
            {
                'code':        'CS2',
                'description': 'fkdjkfjd',
                'gas':         ['GA-1', 'GA-2', 'GA-3', 'GA-5', 'GA-6', 'GA-7', 'GA-8', 'GA-10'],
            },
            {
                'code':        'CSPO1',
                'description': 'Critical thinking',
                'gas':         ['GA-1', 'GA-2', 'GA-3', 'GA-6', 'GA-8', 'GA-9'],
            },
            {
                'code':        'PO3',
                'description': 'Critical thinking',
                'gas':         ['GA-1', 'GA-2', 'GA-6', 'GA-7'],
            },
            {
                'code':        'PO4',
                'description': 'From Frontene',
                'gas':         ['GA-1', 'GA-3', 'GA-4', 'GA-8', 'GA-9', 'GA-10'],
            },
        ]

        for po_data in pos_data:
            po, created = ProgramObjective.objects.get_or_create(
                program=ct1,
                code=po_data['code'],
                defaults={'description': po_data['description']}
            )
            self.stdout.write(f'  {"Created" if created else "Exists "} PO: {po_data["code"]}')

            # Sync GA mappings
            if created:
                for ga_code in po_data['gas']:
                    POGAMapping.objects.get_or_create(
                        program_objective=po,
                        graduate_attribute=gas[ga_code]
                    )

        # ── Users ─────────────────────────────────────────────────────────────
        users_data = [
            {'username': 'ali',  'email': 'ali@ali.com', 'password': 'ali123',  'role': 'student',  'superuser': True},
            {'username': 'zam',  'email': 'zam@zam.com', 'password': 'zam123',  'role': 'student',  'superuser': True},
            {'username': 'qa',   'email': 'qa@qa.com',   'password': 'qa1234',  'role': 'qa',       'superuser': False},
            {'username': 'test', 'email': '',             'password': 'test123', 'role': 'student',  'superuser': False},
        ]

        for u in users_data:
            if not User.objects.filter(username=u['username']).exists():
                user = User.objects.create_user(
                    username=u['username'],
                    email=u['email'],
                    password=u['password'],
                    role=u['role'],
                )
                user.is_superuser = u['superuser']
                user.is_staff     = u['superuser']
                user.save()
                self.stdout.write(f'  Created  User: {u["username"]} (password: {u["password"]})')
            else:
                self.stdout.write(f'  Exists   User: {u["username"]}')

        self.stdout.write(self.style.SUCCESS('\nDatabase seeded successfully!'))
        self.stdout.write('\nLogin credentials:')
        self.stdout.write('  ali  / ali123  (superuser)')
        self.stdout.write('  zam  / zam123  (superuser)')
        self.stdout.write('  qa   / qa1234  (QA)')
        self.stdout.write('  test / test123 (student)')