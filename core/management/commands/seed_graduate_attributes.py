"""
Management command: seed_graduate_attributes

Seeds the 12 Washington Accord Graduate Attributes for every
active (Department, Program) combination in the database.

Usage:
    python manage.py seed_graduate_attributes
    python manage.py seed_graduate_attributes --dept computing
    python manage.py seed_graduate_attributes --force   # overwrite existing names/descriptions

GAs are stored with ga_id = "{PROGRAM_CODE}{NUM}" e.g. "BSCS1", "BSCS2" ...
A ga_id alias index is also maintained so that "GA-1", "GA1", "BSCS1" all
resolve to the same record via the _resolve_ga() helper imported by views.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import GraduateAttribute, Department, Program

# Washington Accord 12 Graduate Attributes (HEC standard for Pakistani universities)
WASHINGTON_ACCORD_GAS = [
    (1,  "Engineering Knowledge",
         "Apply knowledge of mathematics, science, engineering fundamentals and engineering specialisation to the solution of complex engineering problems."),
    (2,  "Problem Analysis",
         "Identify, formulate, research literature and analyse complex engineering problems reaching substantiated conclusions using first principles of mathematics, natural sciences and engineering sciences."),
    (3,  "Design/Development of Solutions",
         "Design solutions for complex engineering problems and design systems, components or processes that meet specified needs with appropriate consideration for public health and safety, cultural, societal, and environmental considerations."),
    (4,  "Investigation",
         "Conduct investigations of complex problems using research-based knowledge and research methods including design of experiments, analysis and interpretation of data, and synthesis of information to provide valid conclusions."),
    (5,  "Modern Tool Usage",
         "Create, select and apply appropriate techniques, resources, and modern engineering and IT tools, including prediction and modelling, to complex engineering activities, with an understanding of the limitations."),
    (6,  "The Engineer and Society",
         "Apply reasoning informed by contextual knowledge to assess societal, health, safety, legal and cultural issues and the consequent responsibilities relevant to professional engineering practice and solutions to complex engineering problems."),
    (7,  "Environment and Sustainability",
         "Understand and evaluate the sustainability and impact of professional engineering work in the solution of complex engineering problems in societal and environmental contexts."),
    (8,  "Ethics",
         "Apply ethical principles and commit to professional ethics and responsibilities and norms of engineering practice."),
    (9,  "Individual and Team Work",
         "Function effectively as an individual, and as a member or leader in diverse teams and in multi-disciplinary settings."),
    (10, "Communication",
         "Communicate effectively on complex engineering activities with the engineering community and with society at large, such as being able to comprehend and write effective reports and design documentation, make effective presentations, and give and receive clear instructions."),
    (11, "Project Management",
         "Demonstrate knowledge and understanding of engineering and management principles and apply these to one's own work, as a member and leader in a team, to manage projects and in multidisciplinary environments."),
    (12, "Lifelong Learning",
         "Recognise the need for, and have the preparation and ability to engage in independent and life-long learning in the broadest context of technological change."),
]


class Command(BaseCommand):
    help = 'Seed Washington Accord Graduate Attributes for all active programs'

    def add_arguments(self, parser):
        parser.add_argument('--dept',  type=str, help='Seed only for this dept_id (e.g. computing)')
        parser.add_argument('--force', action='store_true', help='Overwrite existing GA names/descriptions')

    def handle(self, *args, **options):
        dept_filter = options.get('dept')
        force       = options.get('force', False)

        depts = Department.objects.all()
        if dept_filter:
            depts = depts.filter(dept_id=dept_filter)

        if not depts.exists():
            self.stderr.write(self.style.ERROR('No departments found. Create departments first.'))
            return

        total_created = 0
        total_updated = 0
        total_skipped = 0

        with transaction.atomic():
            for dept in depts:
                programs = Program.objects.filter(department=dept)
                if not programs.exists():
                    self.stdout.write(f'  Dept "{dept.dept_id}" has no programs — skipping')
                    continue

                for program in programs:
                    self.stdout.write(f'\nSeeding GAs for {dept.dept_id} / {program.code}:')
                    for num, name, description in WASHINGTON_ACCORD_GAS:
                        ga_id = f'{program.code}{num}'   # e.g. BSCS1, BSCS8, CS1
                        defaults = {'name': name, 'department': dept, 'program': program}
                        if force:
                            defaults['description'] = description

                        ga, created = GraduateAttribute.objects.get_or_create(
                            ga_id=ga_id,
                            defaults={**defaults, 'description': description}
                        )

                        if created:
                            total_created += 1
                            self.stdout.write(f'  ✓ Created  {ga_id} — {name}')
                        elif force:
                            ga.name        = name
                            ga.description = description
                            ga.department  = dept
                            ga.program     = program
                            ga.save()
                            total_updated += 1
                            self.stdout.write(f'  ↻ Updated  {ga_id} — {name}')
                        else:
                            total_skipped += 1
                            self.stdout.write(f'  — Exists   {ga_id} — {name}')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Created: {total_created}  Updated: {total_updated}  Skipped: {total_skipped}'
        ))
