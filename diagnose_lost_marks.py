"""
READ-ONLY: are the marks deleted, or still in the database but not showing?
Writes nothing.

    python manage.py shell -c "exec(open('diagnose_lost_marks.py').read())" > lost.txt 2>&1
    cat lost.txt

Optional: only one teacher (part of name or email):
    TEACHER=imran python manage.py shell -c "exec(open('diagnose_lost_marks.py').read())" > lost.txt 2>&1
"""
import os
from django.db.models import Q, Count, Min, Max
from core.models import (InstructorCourse, CourseStudent, StudentMark, OBEStudentMark,
                         OBEQuestion, AdmissionStudent)

TEACHER = os.environ.get('TEACHER', '').strip()
qs = InstructorCourse.objects.select_related('instructor__user', 'program').order_by('instructor__user__first_name', 'code', 'academic_year')
if TEACHER:
    qs = qs.filter(Q(instructor__user__first_name__icontains=TEACHER) | Q(instructor__user__last_name__icontains=TEACHER)
                   | Q(instructor__user__email__icontains=TEACHER) | Q(instructor__user__username__icontains=TEACHER))

adm = {r.strip().upper() for r in AdmissionStudent.objects.values_list('reg_no', flat=True)}
print('=' * 110)
print('Per course: roster, marks still in the database, and question links')
print('  q_on_unit = questions linked to an assessment (shown on the marks sheet)')
print('  q_detached = questions NOT linked to any assessment (their marks exist but are not shown)')
print('=' * 110)
print(f'{"teacher":<18}{"course":<9}{"term":<13}{"roster":>7}{"unitMk":>8}{"qMarks":>8}{"q_on_unit":>10}{"q_detached":>11}'
      f'{"marksOnDetached":>16}{"notInAdmissions":>16}  student-id range')
tot = {'unit': 0, 'q': 0, 'det': 0}
for ic in qs:
    roster = ic.students.count()
    unit_mk = StudentMark.objects.filter(student__course=ic).count()
    q_mk = OBEStudentMark.objects.filter(student__course=ic).count()
    q_on = OBEQuestion.objects.filter(course=ic, unit_item__isnull=False).count()
    q_det = OBEQuestion.objects.filter(course=ic, unit_item__isnull=True).count()
    mk_det = OBEStudentMark.objects.filter(question__course=ic, question__unit_item__isnull=True).count()
    regs = list(ic.students.values_list('reg_no', flat=True))
    not_adm = sum(1 for r in regs if r.strip().upper() not in adm)
    rng = ic.students.aggregate(a=Min('id'), b=Max('id'))
    if not (roster or unit_mk or q_mk or q_on or q_det):
        continue
    name = (ic.instructor.user.get_full_name() or ic.instructor.user.username)[:17]
    print(f'{name:<18}{ic.code:<9}{(ic.academic_year or "-"):<13}{roster:>7}{unit_mk:>8}{q_mk:>8}{q_on:>10}{q_det:>11}'
          f'{mk_det:>16}{not_adm:>16}  {rng["a"]}-{rng["b"]}')
    tot['unit'] += unit_mk; tot['q'] += q_mk; tot['det'] += mk_det
print('-' * 110)
print(f'Total unit marks: {tot["unit"]}   per-question marks: {tot["q"]}   marks on detached questions: {tot["det"]}')
print(f'Marks rows in whole database: unit {StudentMark.objects.count()}, per-question {OBEStudentMark.objects.count()}')
print('=' * 110)
