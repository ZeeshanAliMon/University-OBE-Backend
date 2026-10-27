"""
READ-ONLY diagnosis for the CS reports. Writes nothing.

    python manage.py shell -c "exec(open('diagnose_cs_reports.py').read())"

Prints:
  1. Graduate Attributes of the CS program/department, with how many courses,
     CLOs and POs use each one.
  2. GA attainment computed RIGHT NOW with the code on disk — compare with
     what the website shows. If they differ, the web app has not been
     reloaded since `git pull` (PythonAnywhere > Web tab > Reload).
  3. Per-offering roster/marks summary (what feeds the averages).
"""
import inspect
from collections import defaultdict
from core.models import (Program, GraduateAttribute, Course, CLO, POGAMapping,
                         InstructorCourse, AdmissionStudent, OBEStudentMark, User)
import core.views as V

PROGRAM_CODE = 'BSCS'
prog = Program.objects.select_related('department').get(code__iexact=PROGRAM_CODE)
dept = prog.department
print('=' * 78)
print(f'Program {prog.code} - {prog.name} | Department {dept.dept_id} - {dept.name}')
fixed = 'q.course_id == ic.id' in inspect.getsource(V._sheet_course_total)
print('Two-term fix present in code on disk:', 'YES' if fixed else 'NO (git pull needed)')

print('\n1. GRADUATE ATTRIBUTES (department-wide or this program)')
print('-' * 78)
print(f'{"ga_id":<14}{"program":<9}{"courses":>8}{"CLOs":>6}{"POs":>5}  name')
from django.db.models import Q
gas = GraduateAttribute.objects.filter(Q(department=dept)).select_related('program').order_by('ga_id')
for g in gas:
    n_courses = g.courses.filter(program=prog).count()
    n_clos = CLO.objects.filter(mapped_ga=g, course__program=prog).count()
    n_pos = POGAMapping.objects.filter(graduate_attribute=g).count()
    print(f'{g.ga_id:<14}{(g.program.code if g.program else "-"):<9}{n_courses:>8}{n_clos:>6}{n_pos:>5}  {g.name}')
other = GraduateAttribute.objects.exclude(department=dept).count()
print(f'(GAs in other departments: {other})')

print('\n2. GA ATTAINMENT REPORT computed now (same endpoint the QA page calls)')
print('-' * 78)
from rest_framework.test import APIRequestFactory, force_authenticate
qa = User.objects.filter(role='qa').first()
try:
    req = APIRequestFactory().get('/api/reports/program-ga-attainment/', {'programId': prog.code.lower()})
    force_authenticate(req, user=qa)
    r = V.ProgramGAAttainmentView.as_view()(req)
    for a in r.data['attributes']:
        print(f"  {a['id']:<14}{a['averageAttainment']:>7.1f}%   courses {a['contributingCoursesCount']}")
except Exception as e:
    print('  could not compute:', type(e).__name__, e)

print('\n3. OFFERINGS (code, term, roster, CS students, students with marks, avg total)')
print('-' * 78)
cs_regs = {x.strip().upper() for x in AdmissionStudent.objects.filter(program=prog).values_list('reg_no', flat=True)}
rows = 0
unmarked = []
for ic in InstructorCourse.objects.filter(program=prog).order_by('code', 'academic_year', 'id'):
    studs = list(ic.students.all())
    if not studs:
        continue
    marked = set(OBEStudentMark.objects.filter(student__course=ic).values_list('student_id', flat=True))
    totals = [V._sheet_course_total(s)['total'] for s in studs]
    n_cs = sum(1 for s in studs if s.reg_no.strip().upper() in cs_regs)
    avg = sum(totals) / len(totals)
    print(f'  {ic.code:<9}{(ic.academic_year or "-"):<13}{ic.status:<7} roster {len(studs):>3}  CS {n_cs:>3}  '
          f'marked {len(marked):>3}  avg {avg:5.1f}  id {ic.frontend_id}')
    rows += 1
    if not marked:
        unmarked.append((ic, len(studs)))
print(f'({rows} offerings with students)')
print(f'\nOfferings WITH students but NO marks: {len(unmarked)} '
      f'({sum(n for _, n in unmarked)} student rows) - the GA report counts each of these students as 0%.')
print('=' * 78)
