"""
Management command: ensure_accounts
Creates specific user accounts and their profiles if they don't exist.
Safe to run multiple times — uses get_or_create everywhere.
Called manually after seed on PythonAnywhere.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from core.models import User, Department, AdmissionProfile, DeptAdminProfile


ACCOUNTS = [
    # (email, first, last, role, password, profile_type, dept_slug, emp_id)
    ('zeeshan@ali.com',  'Zeeshan', 'Ali', 'admission',  'ijijijij', 'admission',  'computing', 'ADM-ZA-001'),
    ('ali@zeeshan.com',  'Zeeshan', 'Ali', 'dept_admin', 'ijijijij', 'dept_admin', 'computing', 'DA-ZA-001'),
]


class Command(BaseCommand):
    help = 'Ensure specific user accounts exist (idempotent)'

    def handle(self, *args, **kwargs):
        for email, first, last, role, password, profile_type, dept_slug, emp_id in ACCOUNTS:
            # Create user if not exists
            user, created = User.objects.get_or_create(
                email__iexact=email,
                defaults=dict(
                    username=email,
                    email=email,
                    first_name=first,
                    last_name=last,
                    role=role,
                    password=make_password(password),
                    is_active=True,
                )
            )
            status = 'Created' if created else 'Exists'
            self.stdout.write(f'  {status}: {email}')

            # Get department
            try:
                dept = Department.objects.get(dept_id=dept_slug)
            except Department.DoesNotExist:
                self.stdout.write(
                    f'    ⚠ Department "{dept_slug}" not found — run seed first, then ensure_accounts'
                )
                continue

            # Create profile if not exists
            if profile_type == 'admission':
                _, p_created = AdmissionProfile.objects.get_or_create(
                    user=user,
                    defaults=dict(department=dept, employee_id=emp_id)
                )
            elif profile_type == 'dept_admin':
                _, p_created = DeptAdminProfile.objects.get_or_create(
                    user=user,
                    defaults=dict(department=dept, employee_id=emp_id)
                )
            else:
                p_created = False

            if p_created:
                self.stdout.write(f'    ✓ Profile created ({profile_type} @ {dept_slug})')
            else:
                self.stdout.write(f'    • Profile exists ({profile_type} @ {dept_slug})')
