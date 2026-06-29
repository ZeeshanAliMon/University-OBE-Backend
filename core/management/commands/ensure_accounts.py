"""
Management command: ensure_accounts

Creates specific user accounts if they don't already exist.
Safe to run multiple times — uses get_or_create everywhere.
Called from wsgi.py on every startup so accounts are always present
even if the database was seeded before they were added.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from core.models import User, Department, AdmissionProfile, DeptAdminProfile


ACCOUNTS = [
    # (email, username, first, last, role, password, profile_type, dept_slug, emp_id)
    ('zeeshan@ali.com',  'zeeshan_admission', 'Zeeshan', 'Ali',
     'admission',   'ijijijij', 'admission',  'computing', 'ADM-ZA-001'),
    ('ali@zeeshan.com',  'zeeshan_dept',      'Zeeshan', 'Ali',
     'dept_admin',  'ijijijij', 'dept_admin', 'computing', 'DA-ZA-001'),
]


class Command(BaseCommand):
    help = 'Ensure specific user accounts exist (idempotent)'

    def handle(self, *args, **kwargs):
        for email, username, first, last, role, password, profile_type, dept_slug, emp_id in ACCOUNTS:
            user, created = User.objects.get_or_create(
                email__iexact=email,
                defaults=dict(
                    username=username, email=email,
                    first_name=first, last_name=last,
                    role=role, password=make_password(password),
                    is_active=True,
                )
            )

            if created:
                self.stdout.write(f'  ✓ Created: {email}')
            else:
                self.stdout.write(f'  • Exists:  {email}')

            # Ensure profile exists
            try:
                dept = Department.objects.get(dept_id=dept_slug)
            except Department.DoesNotExist:
                self.stdout.write(f'    ⚠ Department "{dept_slug}" not found — skipping profile')
                continue

            if profile_type == 'admission':
                AdmissionProfile.objects.get_or_create(
                    user=user,
                    defaults=dict(department=dept, employee_id=emp_id)
                )
            elif profile_type == 'dept_admin':
                DeptAdminProfile.objects.get_or_create(
                    user=user,
                    defaults=dict(department=dept, employee_id=emp_id)
                )
