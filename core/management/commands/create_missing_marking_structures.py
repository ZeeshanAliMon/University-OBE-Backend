"""
Management command to create missing MarksCategories for courses
Usage: python manage.py create_missing_marking_structures
"""

import json
from django.core.management.base import BaseCommand
from core.models import Course, MarksCategory, UnitItem


class Command(BaseCommand):
    help = 'Create missing marking structures (categories & units) for courses'

    def handle(self, *args, **options):
        courses_without_structure = Course.objects.filter(
            markscategories__isnull=True
        ).distinct()
        
        count = courses_without_structure.count()
        self.stdout.write(f'Found {count} courses without marking structure')
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('All courses have marking structures!'))
            return
        
        categories_created = 0
        units_created = 0
        
        for course in courses_without_structure:
            self.stdout.write(f'  Creating for {course.code}...')
            
            # Standard structure: Assignment (30%, 2 units), Mid (30%, 1 unit), Final (40%, 1 unit)
            category_specs = [
                ("Assignment", 30, 2),
                ("Mid Term", 30, 1),
                ("Final", 40, 1),
            ]
            
            for order, (name, pct, num_units) in enumerate(category_specs):
                cat = MarksCategory.objects.create(
                    course=course,
                    name=name,
                    percentage=pct,
                    units=num_units,
                    order=order
                )
                categories_created += 1
                
                # Create units for this category
                for unit_no in range(1, num_units + 1):
                    total_marks = 15 if num_units > 1 else (30 if name == "Mid Term" else 40)
                    weightage = 100.0 / num_units
                    
                    UnitItem.objects.create(
                        category=cat,
                        unit_no=unit_no,
                        total_marks=total_marks,
                        weightage=weightage,
                        passing=total_marks * 0.5,
                        mapped_clos=json.dumps([])
                    )
                    units_created += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Created {categories_created} categories with {units_created} units'
            )
        )
