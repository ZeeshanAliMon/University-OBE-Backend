"""
Seed assessments, CLO-mapped questions and random marks for the CS program,
so the QA / Dept Admin / Instructor / Student reports have realistic data.

ONLY TOUCHES
    * InstructorCourse offerings whose program is the CS program (PROGRAM,
      default "BSCS"), that are ACTIVE (not closed), have CS students on the
      roster, and have NO marks yet.
    * Only roster students registered in the CS program get marks.
    Nothing else — other programs, other departments, closed courses, courses
    that already have marks — is read-for-change or written.

NEVER DELETES ANYTHING (except in UNDO mode, see below).

WHAT IT WRITES — exactly what the Instructor dashboard writes when a teacher
sets up a course and enters marks by hand:
    CLOs          CLO-1..CLO-4 (theory) / CLO-1..CLO-3 (lab), each mapped to one
                  of the GAs that QA mapped to the course. Only if the course
                  has no CLOs yet — existing CLOs are used as they are.
    Assessments   Theory: Assignments 15% (3), Quizzes 10% (3), Mid Term 25%,
                  Final 50%.  Lab: Lab Reports 15% (4), Lab Performance 15% (2),
                  Viva 10%, Mid Term 20%, Final 40%.
                  If the course's weightages were already set up by the
                  instructor (adding to 100%), that structure is kept and only
                  questions are added to units that have none.
                  The assessment plan belongs to the course, so every term /
                  section of the same course uses the same plan; each term gets
                  its own questions (same layout) and its own marks.
    Questions     "Question 1..n" per unit, each mapped to ONE CLO; every CLO is
                  covered. Unit total = sum of its questions.
    Marks         Every CS student gets a mark on every question (per-question
                  OBE mark + unit total), drawn from a realistic spread:
                  most students 55-90%, a few weak students (at-risk report).
                  Marks are reproducible (same SEED -> same marks).

LEFTOVER WEIGHTAGES
    If a course's weightages are unusable (not adding to 100%, or set on names
    the Instructor dashboard doesn't show, e.g. "Final Exam" from the old demo
    seed) AND the course has no marks anywhere, the standard plan replaces
    them: those leftover categories are set to 0% (not deleted; undo restores
    them).

SKIPPED (and listed, with the reason)
    * course closed / no CS students / already has marks
    * weightages unusable AND the course already has marks somewhere
    * course not linked to a catalog course

USAGE (run from the folder that has manage.py; back up db.sqlite3 first)
    1. Dry run — prints the plan, writes nothing:
         python manage.py shell -c "exec(open('seed_cs_assessments_and_marks.py').read())"
    2. Apply (one transaction: everything or nothing):
         APPLY=1 python manage.py shell -c "exec(open('seed_cs_assessments_and_marks.py').read())"
       It saves a log file  seed_cs_marks_log_<date-time>.json  listing every
       row it created/changed.
    3. Undo a run (uses that log; dry run first, then APPLY=1):
         UNDO=seed_cs_marks_log_<date-time>.json python manage.py shell -c "exec(open('seed_cs_assessments_and_marks.py').read())"
         UNDO=seed_cs_marks_log_<date-time>.json APPLY=1 python manage.py shell -c "exec(open('seed_cs_assessments_and_marks.py').read())"

OPTIONS (environment variables)
    PROGRAM=BSCS            program code to seed (default BSCS)
    ONLY_COURSES=CMC111,CMC112   limit to these course codes
    SEED=2026               change to get a different (still reproducible) spread
"""
import os
import json
import math
import random
import string
import time
from collections import defaultdict
from datetime import datetime

from django.db import transaction

from core.models import (
    Program, AdmissionStudent, Student, InstructorCourse, CourseStudent, CLO,
    MarksCategory, UnitItem, OBEQuestion, StudentMark, OBEStudentMark,
    GraduateAttribute,
)

APPLY        = os.environ.get('APPLY') == '1'
UNDO_FILE    = os.environ.get('UNDO', '').strip()
FORCE        = os.environ.get('FORCE') == '1'
PROGRAM_CODE = os.environ.get('PROGRAM', 'BSCS').strip()
ONLY         = {c.strip().upper() for c in os.environ.get('ONLY_COURSES', '').split(',') if c.strip()}
SEED         = os.environ.get('SEED', '2026').strip()

# ── Must match the Instructor dashboard (InstructorDashboard.tsx) ─────────────
THEORY_CATEGORY_NAMES = ['Assignments', 'Quizzes', 'Class Participation', 'Class Project',
                         'Presentation', 'Problem Based Learning', 'Other Activities',
                         'Mid Term', 'Final']
LAB_CATEGORY_NAMES = ['Mid Term', 'Final', 'Lab Reports', 'Lab Performance', 'Viva',
                      'Assignments', 'Quizzes', 'Open Ended Lab', 'Other Activities', 'Project']

# (category, weight %, [question max marks per unit])
THEORY_PLAN = [
    ('Assignments', 15, [[5, 5], [5, 5], [5, 5]]),
    ('Quizzes',     10, [[10], [10], [10]]),
    ('Mid Term',    25, [[5, 5, 5, 5, 5, 5]]),
    ('Final',       50, [[10, 10, 10, 10, 10]]),
]
LAB_PLAN = [
    ('Lab Reports',     15, [[10], [10], [10], [10]]),
    ('Lab Performance', 15, [[5, 5], [5, 5]]),
    ('Viva',            10, [[10]]),
    ('Mid Term',        20, [[5, 5, 10]]),
    ('Final',           40, [[10, 10, 10, 10]]),
]
THEORY_CLOS = [
    'Describe the fundamental concepts and terminology of {t}.',
    'Apply the core techniques of {t} to solve well-defined problems.',
    'Analyze problems in {t} and evaluate alternative solutions.',
    'Design and implement a solution using the methods of {t}.',
]
LAB_CLOS = [
    'Use the tools and environment required for {t}.',
    'Implement and test lab tasks for {t}.',
    'Document and present the results of lab work in {t}.',
]


def line(ch='='):
    print(ch * 78)


def is_lab(ic):
    # Same rule as normalizeCourse() in InstructorDashboard.tsx
    code = (ic.code or '').strip().upper()
    title = (ic.title or '').strip().lower()
    return code.endswith('L') or 'lab' in title or (ic.course_type or '').lower() == 'lab'


def unit_weights(n):
    # Same as distributeUnitWeightages() in InstructorDashboard.tsx
    if n <= 0:
        return []
    if n == 1:
        return [100.0]
    share = round(100.0 / n, 1)
    return [share] * (n - 1) + [round(100 - share * (n - 1), 1)]


def new_qid(rng, used):
    # Same shape as the dashboard's "Add Question": q-<ms>-<4 chars>
    while True:
        qid = f"q-{int(time.time() * 1000) + rng.randint(0, 999999)}-" + ''.join(
            rng.choice(string.ascii_lowercase + string.digits) for _ in range(4))
        if qid not in used:
            used.add(qid)
            return qid


def split_total(total, n):
    """Split a unit's total marks into n question maxima (0.5 steps, exact sum)."""
    base = math.floor((total / n) * 2) / 2
    parts = [base] * n
    parts[-1] = round(total - base * (n - 1), 1)
    return parts


def ability_for(reg_no):
    r = random.Random(f'{SEED}|student|{reg_no.upper()}')
    if r.random() < 0.08:                       # a few genuinely weak students
        return r.uniform(28, 46)
    return max(35.0, min(96.0, r.gauss(70, 11)))


def score_for(rng, ability, max_marks):
    pct = max(0.0, min(100.0, rng.gauss(ability, 13)))
    val = round((pct / 100.0) * max_marks * 2) / 2   # 0.5 steps like hand entry
    return max(0.0, min(float(max_marks), val))


# ══════════════════════════════════════════════════════════════════════════════
#  UNDO MODE
# ══════════════════════════════════════════════════════════════════════════════
def run_undo():
    line()
    print('UNDO a previous seeding run')
    print('LOG :', UNDO_FILE)
    print('MODE:', 'APPLY - rows will be removed/restored' if APPLY else 'DRY RUN - nothing will be written')
    line()
    with open(UNDO_FILE) as f:
        log = json.load(f)
    c, u = log['created'], log['updated']

    sm_pairs  = {tuple(p) for p in c['student_marks']}
    obe_pairs = {tuple(p) for p in c['obe_marks']}

    # Marks entered by people AFTER the seeding on seeded questions/units would
    # be lost too — refuse unless FORCE=1.
    extra_obe = [om for om in OBEStudentMark.objects.filter(
                     question_id__in=list(c['questions']) + [int(k) for k in u.get('questions', {})])
                 if (om.student_id, om.question_id) not in obe_pairs]
    extra_sm = [sm for sm in StudentMark.objects.filter(unit_item_id__in=c['units'])
                if (sm.student_id, sm.unit_item_id) not in sm_pairs]
    print(f"Seeded per-question marks : {len(obe_pairs)}")
    print(f"Seeded unit marks         : {len(sm_pairs)}")
    print(f"Seeded questions          : {len(c['questions'])}")
    print(f"Seeded units / categories : {len(c['units'])} / {len(c['categories'])}")
    print(f"Seeded CLOs               : {len(c['clos'])}")
    print(f"Settings to restore       : {len(u['categories'])} categories, {len(u['units'])} units, "
          f"{len(u.get('questions', {}))} questions, {len(u['courses'])} courses")
    if extra_obe or extra_sm:
        print(f"\n!! {len(extra_obe) + len(extra_sm)} marks were entered AFTER seeding on seeded questions/units.")
        print("   Undo would delete them too. Re-run with FORCE=1 if that is what you want.")
        if not FORCE:
            return
    if not APPLY:
        print('\nNothing written. Add APPLY=1 to undo for real.')
        return

    with transaction.atomic():
        sm_ids  = [sm.id for sm in StudentMark.objects.filter(unit_item_id__in={p[1] for p in sm_pairs})
                   if (sm.student_id, sm.unit_item_id) in sm_pairs]
        obe_ids = [om.id for om in OBEStudentMark.objects.filter(question_id__in={p[1] for p in obe_pairs})
                   if (om.student_id, om.question_id) in obe_pairs]
        StudentMark.objects.filter(id__in=sm_ids).delete()
        OBEStudentMark.objects.filter(id__in=obe_ids).delete()
        if FORCE:
            OBEStudentMark.objects.filter(id__in=[x.id for x in extra_obe]).delete()
            StudentMark.objects.filter(id__in=[x.id for x in extra_sm]).delete()
        OBEQuestion.objects.filter(id__in=c['questions']).delete()
        for pk, prev in u.get('questions', {}).items():
            OBEQuestion.objects.filter(pk=int(pk)).update(**prev)
        for pk, prev in u['units'].items():
            UnitItem.objects.filter(pk=int(pk)).update(**prev)
        UnitItem.objects.filter(id__in=c['units']).delete()
        for pk, prev in u['categories'].items():
            MarksCategory.objects.filter(pk=int(pk)).update(**prev)
        MarksCategory.objects.filter(id__in=c['categories']).delete()
        CLO.objects.filter(id__in=c['clos']).delete()
        for pk, prev in u['courses'].items():
            InstructorCourse.objects.filter(pk=int(pk)).update(**prev)
    print('\nUndo complete. The seeded data has been removed and changed settings restored.')


# ══════════════════════════════════════════════════════════════════════════════
#  SEED MODE
# ══════════════════════════════════════════════════════════════════════════════
def run_seed():
    line()
    print('SEED CS ASSESSMENTS, CLO-MAPPED QUESTIONS AND MARKS')
    print('MODE:', 'APPLY - changes will be saved' if APPLY else 'DRY RUN - nothing will be written')
    line()

    try:
        prog = Program.objects.select_related('department').get(code__iexact=PROGRAM_CODE)
    except Program.DoesNotExist:
        print(f'Program "{PROGRAM_CODE}" not found. Programs in the database:')
        for p in Program.objects.select_related('department').order_by('code'):
            print(f'   {p.code:<12} {p.name}  ({p.department.name})')
        print('Re-run with PROGRAM=<code>.')
        return
    dept = prog.department
    print(f'Program    : {prog.code} - {prog.name}')
    print(f'Department : {dept.dept_id} - {dept.name}')
    if ONLY:
        print(f'Only       : {", ".join(sorted(ONLY))}')

    cs_regs = {r.strip().upper() for r in AdmissionStudent.objects.filter(program=prog).values_list('reg_no', flat=True)}
    cs_regs |= {r.strip().upper() for r in Student.objects.filter(program=prog).values_list('reg_no', flat=True)}
    print(f'CS students registered: {len(cs_regs)}')

    course_gas_cache = {}

    def eligible_gas(ic):
        # GAs QA mapped to this course, that a CLO of this course may use
        # (same department; program-less or this program) — as _resolve_ga allows.
        cc = ic.catalog_course
        if cc.pk not in course_gas_cache:
            gas = [g for g in cc.mapped_gas.all().order_by('ga_id')
                   if g.department_id == ic.department_id and (g.program_id is None or g.program_id == ic.program_id)]
            course_gas_cache[cc.pk] = gas
        return course_gas_cache[cc.pk]

    offerings = (InstructorCourse.objects.filter(program=prog)
                 .select_related('catalog_course', 'instructor__user', 'department')
                 .order_by('code', 'academic_year', 'id'))

    plans, skipped = [], []
    warn_no_ga = []
    planned_catalogs = {}   # catalog course pk -> is_lab, for courses seeded in this run

    for ic in offerings:
        label = f"{ic.code} {ic.title[:34]:<34} {ic.academic_year or '-':<12} {(ic.instructor.user.get_full_name() or ic.instructor.user.username)[:20]}"
        if ONLY and ic.code.upper() not in ONLY:
            continue
        if ic.status == 'closed':
            skipped.append((label, 'closed / finalized'))
            continue
        cc = ic.catalog_course
        if cc is None:
            skipped.append((label, 'not linked to a catalog course'))
            continue
        roster = list(ic.students.all())
        cs_roster = [s for s in roster if s.reg_no.strip().upper() in cs_regs]
        if not cs_roster:
            skipped.append((label, 'no CS students on the roster'))
            continue
        if (StudentMark.objects.filter(student__course=ic).exists()
                or OBEStudentMark.objects.filter(student__course=ic).exists()):
            skipped.append((label, 'already has marks'))
            continue
        lab = is_lab(ic)
        replace_note = None
        allowed = LAB_CATEGORY_NAMES if lab else THEORY_CATEGORY_NAMES
        cats = list(cc.markscategories.all())
        weighted = [c for c in cats if c.percentage > 0]
        if cc.pk in planned_catalogs:
            # Another term/section of this course is seeded earlier in this run
            # and creates the plan; this one reuses it.
            if planned_catalogs[cc.pk] != lab:
                skipped.append((label, 'other term of this course is set up as the other type (Theory/Lab)'))
                continue
            mode = 'sibling'
        elif not weighted:
            mode = 'new'
        else:
            total = sum(c.percentage for c in weighted)
            bad_names = [c.name for c in weighted if c.name not in allowed]
            no_units = [c.name for c in weighted if c.units <= 0]
            problem = None
            if bad_names:
                problem = f'weightage on categories the {"Lab" if lab else "Theory"} sheet does not show: {", ".join(bad_names)}'
            elif abs(total - 100) > 0.5:
                problem = f'weightages add up to {total:g}%, not 100%'
            elif no_units:
                problem = f'weighted categories with 0 units: {", ".join(no_units)}'
            if problem is None:
                mode = 'existing'
            else:
                structure_has_marks = (
                    StudentMark.objects.filter(unit_item__category__course=cc).exists()
                    or OBEStudentMark.objects.filter(question__unit_item__category__course=cc).exists())
                if structure_has_marks:
                    skipped.append((label, problem + ' - and the course already has marks, so it is left for you'))
                    continue
                mode = 'new'
                replace_note = ', '.join(f'{c.name} {c.percentage:g}%' for c in weighted)

        planned_catalogs.setdefault(cc.pk, lab)
        existing_clos = list(ic.clos.order_by('order', 'code'))
        gas = eligible_gas(ic)
        if not existing_clos and not gas:
            warn_no_ga.append(f'{ic.code} {ic.title}')

        plans.append(dict(ic=ic, lab=lab, mode=mode, cs_roster=cs_roster, replace_note=replace_note,
                          non_cs=len(roster) - len(cs_roster), existing_clos=existing_clos, gas=gas))

    first_mode = {}
    for p in plans:
        first_mode.setdefault(p['ic'].catalog_course_id, p['mode'])

    def plans_existing(p):
        return first_mode.get(p['ic'].catalog_course_id) == 'existing'

    # ── Report ────────────────────────────────────────────────────────────────
    print(f'\nCOURSES TO SEED: {len(plans)}')
    line('-')
    tot_q = tot_m = 0
    for p in plans:
        ic = p['ic']
        if p['mode'] in ('new', 'sibling') and not (p['mode'] == 'sibling' and plans_existing(p)):
            plan = LAB_PLAN if p['lab'] else THEORY_PLAN
            nq = sum(len(u) for _, _, units in plan for u in units)
        else:
            nq = None
        clos = (f"{len(p['existing_clos'])} existing CLOs" if p['existing_clos']
                else f"{len(LAB_CLOS if p['lab'] else THEORY_CLOS)} new CLOs")
        extra = f", {p['non_cs']} non-CS on roster left blank" if p['non_cs'] else ''
        if p.get('replace_note'):
            extra += f"\n              replaces leftover weightages ({p['replace_note']}) with the standard plan"
        print(f"  {ic.code:<9} {ic.title[:36]:<36} {ic.academic_year or '-':<11} "
              f"{'Lab' if p['lab'] else 'Theory':<6} {({'new': 'standard plan', 'existing': 'keeps your weightages', 'sibling': 'same plan as other term'}[p['mode']]):<23} "
              f"{len(p['cs_roster']):>3} students, {clos}{extra}")
        if nq:
            tot_q += nq
            tot_m += nq * len(p['cs_roster'])
    if tot_m:
        print(f"\n  ~{tot_q} questions and ~{tot_m} per-question marks (standard-plan courses)")
    terms = defaultdict(int)
    for p in plans:
        terms[p['ic'].academic_year or '-'] += 1
    print('  by term: ' + ', '.join(f'{t}: {n}' for t, n in sorted(terms.items())))

    print(f'\nSKIPPED: {len(skipped)}')
    line('-')
    for label, why in skipped:
        print(f'  {label}  ->  {why}')

    if warn_no_ga:
        print('\nNOTE: these courses have no GA mapping in QA "Courses to GA mapping",')
        print('      so their new CLOs get no GA (GA reports will not count them).')
        print('      Map them in QA first if you want GA attainment for them:')
        for w in warn_no_ga:
            print('   -', w)

    if not plans:
        print('\nNothing to seed.')
        return
    if not APPLY:
        print('\nDRY RUN - nothing written. Review the lists above, then run again with APPLY=1.')
        return

    # ── Apply ─────────────────────────────────────────────────────────────────
    log = {
        'created': {'clos': [], 'categories': [], 'units': [], 'questions': [],
                    'student_marks': [], 'obe_marks': []},
        'updated': {'categories': {}, 'units': {}, 'courses': {}, 'questions': {}},
        'program': prog.code, 'seed': SEED, 'at': datetime.now().isoformat(timespec='seconds'),
    }
    C, U = log['created'], log['updated']

    seeded_ic_pks = set()
    with transaction.atomic():
        for p in plans:
            ic, lab = p['ic'], p['lab']
            seeded_ic_pks.add(ic.pk)
            cc = ic.catalog_course
            rng = random.Random(f'{SEED}|course|{ic.pk}')
            used_qids = set(OBEQuestion.objects.filter(course=ic).values_list('frontend_id', flat=True))

            # 1. CLOs
            if p['existing_clos']:
                clo_codes = [c.code for c in p['existing_clos']]
            else:
                templates = LAB_CLOS if lab else THEORY_CLOS
                clo_codes = []
                for i, tpl in enumerate(templates, start=1):
                    ga = p['gas'][(i - 1) % len(p['gas'])] if p['gas'] else None
                    clo = CLO.objects.create(course=ic, code=f'CLO-{i}',
                                             description=tpl.format(t=ic.title), mapped_ga=ga, order=i)
                    C['clos'].append(clo.pk)
                    clo_codes.append(clo.code)
                if ic.clo_count != len(clo_codes):
                    U['courses'][str(ic.pk)] = {'clo_count': ic.clo_count}
                    InstructorCourse.objects.filter(pk=ic.pk).update(clo_count=len(clo_codes))

            # 2. Categories + units (+ the question layout for each unit)
            unit_layout = []   # (cat_name, UnitItem, [(max, clo or None)] or None to keep existing)
            mode = p['mode']
            if mode == 'sibling':
                mode = 'existing'   # plan was created by the other term earlier in this run
            if mode == 'new':
                plan = LAB_PLAN if lab else THEORY_PLAN
                order_names = LAB_CATEGORY_NAMES if lab else THEORY_CATEGORY_NAMES
                plan_names = {n for n, _, _ in plan}
                # Leftover weightages on categories outside the plan -> 0% (kept, not deleted)
                for old in cc.markscategories.filter(percentage__gt=0).exclude(name__in=plan_names):
                    U['categories'][str(old.pk)] = {'percentage': old.percentage, 'units': old.units, 'order': old.order}
                    MarksCategory.objects.filter(pk=old.pk).update(percentage=0)
                for name, pct, units in plan:
                    cat = cc.markscategories.filter(name=name).first()
                    vals = {'percentage': pct, 'units': len(units), 'order': order_names.index(name)}
                    if cat:
                        U['categories'][str(cat.pk)] = {'percentage': cat.percentage, 'units': cat.units, 'order': cat.order}
                        MarksCategory.objects.filter(pk=cat.pk).update(**vals)
                    else:
                        cat = MarksCategory.objects.create(course=cc, name=name, **vals)
                        C['categories'].append(cat.pk)
                    weights = unit_weights(len(units))
                    for n, maxima in enumerate(units, start=1):
                        total = float(sum(maxima))
                        uvals = {'passing': round(total * 0.5, 1), 'total_marks': total,
                                 'weightage': weights[n - 1], 'mapped_clos': []}
                        ui = UnitItem.objects.filter(category=cat, unit_no=n).first()
                        if ui:
                            U['units'][str(ui.pk)] = {'passing': ui.passing, 'total_marks': ui.total_marks,
                                                      'weightage': ui.weightage, 'mapped_clos': ui.mapped_clos}
                            UnitItem.objects.filter(pk=ui.pk).update(**uvals)
                            ui.refresh_from_db()
                        else:
                            ui = UnitItem.objects.create(category=cat, unit_no=n, **uvals)
                            C['units'].append(ui.pk)
                        unit_layout.append((name, ui, [(m, None) for m in maxima]))
            else:
                for cat in cc.markscategories.filter(percentage__gt=0).order_by('order'):
                    weights = unit_weights(cat.units)
                    for n in range(1, cat.units + 1):
                        ui = UnitItem.objects.filter(category=cat, unit_no=n).first()
                        if not ui:
                            ui = UnitItem.objects.create(category=cat, unit_no=n, passing=5, total_marks=10,
                                                         weightage=weights[n - 1], mapped_clos=[])
                            C['units'].append(ui.pk)
                        # Another term of this course already has questions on this
                        # unit: use the same layout (marks + CLO), with our own ids.
                        sib = None
                        others = list(InstructorCourse.objects.filter(catalog_course=cc).exclude(pk=ic.pk)
                                      .order_by('-academic_year', 'id'))
                        others.sort(key=lambda o: 0 if o.pk in seeded_ic_pks else 1)
                        for other in others:
                            qs_other = list(OBEQuestion.objects.filter(course=other, unit_item=ui).order_by('order', 'id'))
                            if qs_other:
                                sib = qs_other
                                break
                        if sib:
                            unit_layout.append((cat.name, ui, [
                                (q.max_marks, (q.mapped_clos or [None])[0]) for q in sib]))
                        else:
                            total = float(ui.total_marks or 10)
                            nq = 1 if total <= 10 else min(6, max(2, round(total / 10)))
                            unit_layout.append((cat.name, ui, [(m, None) for m in split_total(total, nq)]))

            # 3. Questions (each mapped to one CLO; rotate so every CLO is covered)
            order = OBEQuestion.objects.filter(course=ic).count()
            rot = 0
            unit_questions = []   # (UnitItem, [OBEQuestion])
            for cat_name, ui, maxima in unit_layout:
                target_total = float(sum(m for m, _ in maxima))
                own = list(OBEQuestion.objects.filter(course=ic, unit_item=ui).order_by('order', 'id'))
                if own and abs(sum(q.max_marks or 0 for q in own) - target_total) < 0.01:
                    # This term's own (unmarked) questions already match the unit: keep them.
                    unit_questions.append((ui, own))
                    UnitItem.objects.filter(pk=ui.pk).update(
                        mapped_clos=sorted({c for q in own for c in (q.mapped_clos or [])}))
                    continue
                if len(own) > len(maxima):
                    maxima = [(m, None) for m in split_total(target_total, len(own))]
                qs = []
                for j, (mx, want_clo) in enumerate(maxima, start=1):
                    if want_clo and want_clo in clo_codes:
                        clo_code = want_clo
                    else:
                        clo_code = clo_codes[rot % len(clo_codes)]
                    rot += 1
                    if j <= len(own):
                        # Leftover unmarked question that doesn't fit the unit:
                        # bring it in line with the plan (old values logged for undo).
                        q = own[j - 1]
                        U['questions'][str(q.pk)] = {'max_marks': q.max_marks, 'mapped_clos': q.mapped_clos,
                                                     'question_name': q.question_name}
                        q.max_marks, q.mapped_clos, q.question_name = float(mx), [clo_code], f'Question {j}'
                        q.save(update_fields=['max_marks', 'mapped_clos', 'question_name'])
                    else:
                        q = OBEQuestion.objects.create(
                            course=ic, unit_item=ui, frontend_id=new_qid(rng, used_qids),
                            category_name=cat_name, unit_no=ui.unit_no, question_name=f'Question {j}',
                            max_marks=float(mx), mapped_clos=[clo_code], order=order)
                        order += 1
                        C['questions'].append(q.pk)
                    qs.append(q)
                mapped = sorted({c for q in qs for c in (q.mapped_clos or [])})
                if mode == 'existing' and str(ui.pk) not in U['units'] and ui.pk not in C['units']:
                    U['units'][str(ui.pk)] = {'passing': ui.passing, 'total_marks': ui.total_marks,
                                              'weightage': ui.weightage, 'mapped_clos': ui.mapped_clos}
                UnitItem.objects.filter(pk=ui.pk).update(mapped_clos=mapped)
                unit_questions.append((ui, qs))

            # 4. Marks: per-question OBE marks + unit totals (sum of its questions)
            obe_rows, sm_rows = [], []
            course_offset = random.Random(f'{SEED}|difficulty|{ic.pk}').gauss(0, 5)
            for st in p['cs_roster']:
                ability = ability_for(st.reg_no) + course_offset
                srng = random.Random(f'{SEED}|marks|{ic.pk}|{st.reg_no.upper()}')
                for ui, qs in unit_questions:
                    unit_sum = 0.0
                    for q in qs:
                        sc = score_for(srng, ability, q.max_marks or 0)
                        unit_sum += sc
                        obe_rows.append(OBEStudentMark(student=st, question=q, score=sc))
                        C['obe_marks'].append([st.pk, q.pk])
                    sm_rows.append(StudentMark(student=st, unit_item=ui, score=round(unit_sum, 1)))
                    C['student_marks'].append([st.pk, ui.pk])
            OBEStudentMark.objects.bulk_create(obe_rows, batch_size=500)
            StudentMark.objects.bulk_create(sm_rows, batch_size=500)
            print(f"  seeded {ic.code:<9} {len(p['cs_roster']):>3} students, "
                  f"{sum(len(q) for _, q in unit_questions)} questions, {len(obe_rows)} marks")

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = f'seed_cs_marks_log_{stamp}.json'
    with open(log_path, 'w') as f:
        json.dump(log, f)

    # ── Check: totals as the mark sheet computes them ─────────────────────────
    from core.views import _sheet_course_total
    print('\nRESULT CHECK (course total out of 100, as the instructor mark sheet shows it)')
    line('-')
    for p in plans:
        ic = InstructorCourse.objects.get(pk=p['ic'].pk)
        totals = [_sheet_course_total(s)['total'] for s in ic.students.all()
                  if s.reg_no.strip().upper() in cs_regs]
        if totals:
            below = sum(1 for t in totals if t < 50)
            print(f"  {ic.code:<9} avg {sum(totals) / len(totals):5.1f}   min {min(totals):5.1f}   "
                  f"max {max(totals):5.1f}   below 50: {below}")
    line()
    print(f'Done. Log saved: {log_path}')
    print(f'To undo:  UNDO={log_path} APPLY=1 python manage.py shell -c "exec(open(\'seed_cs_assessments_and_marks.py\').read())"')


if UNDO_FILE:
    run_undo()
else:
    run_seed()
