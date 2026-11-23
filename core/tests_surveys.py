from django.test import TestCase
from rest_framework.test import APIClient

from .models import (
    AdmissionStudent, CLO, Course, CourseStudent, Department, DeptAdminProfile, FinalResult,
    GraduateAttribute, InstructorCourse, InstructorProfile, MarksCategory, OBEQuestion, OBEStudentMark,
    POGAMapping, Program, ProgramObjective, QAProfile, SemesterPlan, SurveyMapping, SurveyResponse, SurveyUpload, UnitItem, User,
)
from .surveys import batch_code, meaningful_comment, parse_rating, parse_year


class AttainmentBase(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_id='computing', name='Computing')
        self.program = Program.objects.create(code='BSCS', name='BS Computer Science', department=self.dept)
        self.gas = [GraduateAttribute.objects.create(ga_id=f'GA-BSCS-{n}', name=f'GA {n}', department=self.dept, program=self.program)
                    for n in range(1, 11)]
        self.po = ProgramObjective.objects.create(program=self.program, code='PO1', description='Knowledge')
        POGAMapping.objects.create(program_objective=self.po, graduate_attribute=self.gas[0])
        self.teacher = InstructorProfile.objects.create(
            user=User.objects.create(username='t@x.com', email='t@x.com', role='instructor'),
            employee_id='T1', department=self.dept)
        self.qa = User.objects.create(username='qa@x.com', email='qa@x.com', role='qa')
        QAProfile.objects.create(user=self.qa, employee_id='QA1', department=self.dept)
        self.admin = User.objects.create(username='da@x.com', email='da@x.com', role='dept_admin')
        DeptAdminProfile.objects.create(user=self.admin, employee_id='DA1', department=self.dept)
        for reg in ('SP23-BSCS-001', 'SP23-BSCS-002'):
            AdmissionStudent.objects.create(reg_no=reg, name=reg, email=f'{reg}@x.com', department=self.dept, program=self.program)

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def offering(self, code, term, marks, status='closed', ga=0):
        """marks = {reg no: percent on the course's one question}, mapped to self.gas[ga]."""
        course, _ = Course.objects.get_or_create(code=code, department=self.dept, program=self.program, defaults={'title': code})
        cat, _ = MarksCategory.objects.get_or_create(course=course, name='Final', defaults={'percentage': 100, 'units': 1})
        unit, _ = UnitItem.objects.get_or_create(category=cat, unit_no=1, defaults={'total_marks': 100, 'weightage': 100})
        ic = InstructorCourse.objects.create(
            frontend_id=f'{code}-{term}', instructor=self.teacher, code=code, title=code, department=self.dept,
            program=self.program, catalog_course=course, academic_year=term, status=status)
        CLO.objects.create(course=ic, code='CLO-1', mapped_ga=self.gas[ga], order=1)
        q = OBEQuestion.objects.create(course=ic, unit_item=unit, frontend_id='q1', category_name='Final', unit_no=1,
                                       question_name='Q1', max_marks=100, mapped_clos=['CLO-1'])
        for reg, pct in marks.items():
            st = CourseStudent.objects.create(course=ic, reg_no=reg, name=reg)
            OBEStudentMark.objects.create(student=st, question=q, score=pct)
        return ic


class DirectAssessmentTests(AttainmentBase):
    def test_course_score_counts_students_and_kpi_counts_courses(self):
        # 1 of 2 students attains = 50%; 0 of 2 = 0%. So 1 of 2 courses attains: KPI met, average 25.
        self.offering('C1', 'Fall-2024', {'SP23-BSCS-001': 90, 'SP23-BSCS-002': 40})
        self.offering('C2', 'Fall-2024', {'SP23-BSCS-001': 40, 'SP23-BSCS-002': 40})
        r = self.client_for(self.qa).get('/api/reports/program-ga-attainment/?programId=BSCS')
        ga = next(a for a in r.data['attributes'] if a['id'] == 'GA-BSCS-1')
        self.assertEqual([c['score'] for c in ga['contributingCourses']], [50.0, 0.0])
        self.assertEqual((ga['averageAttainment'], ga['coursesAttained'], ga['contributingCoursesCount']), (25.0, 1, 2))
        self.assertTrue(ga['kpiMet'])
        self.assertEqual(ga['attainmentStatus'], 'Passed')

    def test_repeated_course_counts_the_best_attempt_once(self):
        self.offering('C1', 'Fall-2024', {'SP23-BSCS-001': 20})
        self.offering('C1', 'Fall-2025', {'SP23-BSCS-001': 80})
        self.offering('C1', 'Spring-2026', {'SP23-BSCS-001': 30})
        r = self.client_for(self.qa).get('/api/reports/program-ga-attainment/?programId=BSCS')
        course = next(a for a in r.data['attributes'] if a['id'] == 'GA-BSCS-1')['contributingCourses'][0]
        self.assertEqual((course['studentCount'], course['score']), (1, 100.0))
        r = self.client_for(self.qa).get('/api/reports/course-attainment/?courseCode=C1&programId=BSCS')
        self.assertEqual(r.data['classSize'], 1)
        self.assertEqual((r.data['clos'][0]['averageMarks'], r.data['clos'][0]['passedCount']), (80.0, 1))

    def two_clo_attempt(self, term, clo1, clo2, reg='SP23-BSCS-001'):
        """An attempt at C1 with one question per CLO, 100 marks each. CLO-1 is GA1, CLO-2 is GA2."""
        ic = self.offering('C1', term, {reg: clo1})
        CLO.objects.create(course=ic, code='CLO-2', mapped_ga=self.gas[1], order=2)
        q2 = OBEQuestion.objects.create(course=ic, unit_item=ic.obe_questions.get().unit_item, frontend_id='q2', category_name='Final',
                                        unit_no=1, question_name='Q2', max_marks=100, mapped_clos=['CLO-2'])
        OBEStudentMark.objects.create(student=ic.students.get(), question=q2, score=clo2)
        return ic

    def test_best_whole_attempt_is_not_mixed_with_another(self):
        # 1st attempt total 60 (CLO-1 40, CLO-2 80); 2nd total 57.5 (CLO-1 70, CLO-2 45).
        # The 1st counts as a whole, so CLO-1 stays 40 and is not attained.
        reg = 'SP23-BSCS-001'
        self.two_clo_attempt('Fall-2024', 40, 80)
        self.two_clo_attempt('Fall-2025', 70, 45)
        c = self.client_for(self.qa)
        clos = {x['code']: x for x in c.get('/api/reports/course-attainment/?courseCode=C1&programId=BSCS').data['clos']}
        self.assertEqual((clos['CLO-1']['averageMarks'], clos['CLO-1']['passedCount']), (40.0, 0))
        self.assertEqual((clos['CLO-2']['averageMarks'], clos['CLO-2']['passedCount']), (80.0, 1))
        attrs = {a['id']: a for a in c.get('/api/reports/program-ga-attainment/?programId=BSCS').data['attributes']}
        self.assertEqual(attrs['GA-BSCS-1']['contributingCourses'][0]['score'], 0.0)
        self.assertEqual(attrs['GA-BSCS-2']['contributingCourses'][0]['score'], 100.0)
        for path, key, value in ((f'/api/reports/student-ga-questions/?regNo={reg}', 'gas', 'percent'),
                                 (f'/api/reports/student-ga-attainment/?regNo={reg}', 'attainments', 'score')):
            rows = c.get(path).data[key]
            self.assertEqual([r[value] for r in rows], [0.0, 100.0], path)
        # Choosing one term looks at that attempt alone.
        clos = {x['code']: x for x in c.get('/api/reports/course-attainment/?courseCode=C1&programId=BSCS&academicYear=Fall-2025').data['clos']}
        self.assertEqual(clos['CLO-1']['averageMarks'], 70.0)

    def test_best_attempt_tie_uses_the_latest(self):
        self.two_clo_attempt('Fall-2024', 40, 80)
        self.two_clo_attempt('Fall-2025', 80, 40)
        clos = {x['code']: x for x in self.client_for(self.qa).get('/api/reports/course-attainment/?courseCode=C1&programId=BSCS').data['clos']}
        self.assertEqual((clos['CLO-1']['averageMarks'], clos['CLO-2']['averageMarks']), (80.0, 40.0))

    def test_student_needs_half_the_courses_and_a_50_average(self):
        reg = 'SP23-BSCS-001'
        self.offering('C1', 'Fall-2024', {reg: 100})
        self.offering('C2', 'Fall-2024', {reg: 0})
        self.offering('C3', 'Fall-2024', {reg: 0})   # 1 of 3 courses, average 33: not attained
        c = self.client_for(self.qa)
        ga = c.get(f'/api/reports/student-ga-questions/?regNo={reg}').data['gas'][0]
        self.assertEqual((ga['coursesAttained'], ga['courseCount'], ga['attained']), (1, 3, False))
        batch = c.get('/api/reports/batch-ga-attainment/?batch=sp23&departmentId=computing&programId=BSCS').data
        self.assertFalse(batch['students'][0]['gaAttained']['GA-BSCS-1'])
        self.assertEqual(next(a for a in batch['attributes'] if a['id'] == 'GA-BSCS-1')['passedCount'], 0)
        self.offering('C4', 'Fall-2024', {reg: 100})   # 2 of 4 courses, average 50: attained
        ga = c.get(f'/api/reports/student-ga-questions/?regNo={reg}').data['gas'][0]
        self.assertEqual((ga['percent'], ga['attained']), (50.0, True))

    def test_co_summary_counts_students_who_attain(self):
        self.offering('C1', 'Fall-2024', {'SP23-BSCS-001': 100, 'SP23-BSCS-002': 10})   # class average 55, 1 of 2 attain
        clo = self.client_for(self.qa).get('/api/reports/co-attainment-summary/?programId=BSCS').data['courses'][0]['clos'][0]
        self.assertEqual((clo['attainmentPercent'], clo['classAverage'], clo['status']), (50.0, 55.0, 'Met'))

    def test_draft_past_course_is_not_counted(self):
        ic = self.offering('C1', 'Fall-2024', {'SP23-BSCS-001': 100}, status='active')
        InstructorCourse.objects.filter(pk=ic.pk).update(is_historical=True)
        r = self.client_for(self.qa).get('/api/reports/program-ga-attainment/?programId=BSCS')
        self.assertEqual(r.data['studentCount'], 0)


class CohortAndSurveyTests(AttainmentBase):
    def upload(self, form, rows, year=2026, **extra):
        return self.client_for(self.qa).post('/api/surveys/uploads/', {
            'formType': form, 'year': year, 'fileName': 'r.xlsx', 'rows': rows, **extra}, format='json')

    def graduate(self):
        SemesterPlan.objects.create(program=self.program, semester='8th', course_codes=['C8'])
        self.offering('C8', 'Spring-2026', {'SP23-BSCS-001': 90, 'SP23-BSCS-002': 40})

    def test_batch_graduates_when_its_8th_semester_is_finalized(self):
        SemesterPlan.objects.create(program=self.program, semester='8th', course_codes=['C8', 'C9'])
        self.offering('C8', 'Spring-2026', {'SP23-BSCS-001': 90})
        open_course = self.offering('C9', 'Spring-2026', {'SP23-BSCS-001': 90}, status='active')
        c = self.client_for(self.qa)
        self.assertEqual(c.get('/api/reports/cohort-ga/?programId=BSCS').data['graduatedBatches'], [])
        InstructorCourse.objects.filter(pk=open_course.pk).update(status='closed')
        self.assertEqual(c.get('/api/reports/cohort-ga/?programId=BSCS').data['graduatedBatches'], ['SP23'])

    def test_cohort_is_80_direct_20_indirect_for_graduated_batches_only(self):
        self.graduate()    # direct: 1 of 2 graduates attains = 50
        AdmissionStudent.objects.create(reg_no='FA24-BSCS-001', name='N', email='n@x.com', department=self.dept, program=self.program)
        self.offering('C1', 'Fall-2025', {'FA24-BSCS-001': 0})   # not graduated: left out
        self.upload('internship', [
            {'program': 'BSCS', 'regNo': 'SP23-BSCS-001', 'ratings': {'1': 5}},
            {'program': 'BSCS', 'regNo': 'SP23-BSCS-002', 'ratings': {'1': 2}},
            {'program': 'BSCS', 'regNo': 'FA24-BSCS-001', 'ratings': {'1': 1}},   # not graduated: left out
        ])
        self.upload('exit', [{'program': 'BSCS', 'batch': 'CS-SP-23', 'ratings': {'1': 3}}])
        data = self.client_for(self.qa).get('/api/reports/cohort-ga/?programId=BSCS').data
        ga = data['attributes'][0]
        self.assertEqual(data['graduatedBatches'], ['SP23'])
        self.assertEqual((ga['direct'], ga['mappedCourses']), (50.0, 1))
        self.assertEqual((ga['internship'], ga['exit'], ga['indirect']), (50.0, 100.0, 75.0))
        self.assertEqual(ga['combined'], 55.0)   # 50 x 0.8 + 75 x 0.2
        self.assertTrue(ga['attained'])
        self.assertIsNone(data['attributes'][1]['combined'])   # GA2 has neither

    def test_cohort_weights_are_configurable(self):
        self.graduate()    # direct 50
        self.upload('exit', [{'program': 'BSCS', 'batch': 'SP23', 'ratings': {'1': 5}}])    # indirect 100
        c = self.client_for(self.qa)
        self.assertEqual(c.get('/api/reports/cohort-ga/?programId=BSCS').data['attributes'][0]['combined'], 60.0)
        self.assertEqual(c.patch('/api/departments/computing/', {'directWeight': 70}, format='json').status_code, 200)
        data = c.get('/api/reports/cohort-ga/?programId=BSCS').data
        self.assertEqual((data['directWeight'], data['indirectWeight']), (70, 30))
        self.assertEqual(data['attributes'][0]['combined'], 65.0)
        # At 100% direct, no survey is needed for a combined result.
        c.patch('/api/departments/computing/', {'directWeight': 100}, format='json')
        self.assertEqual(c.get('/api/reports/cohort-ga/?programId=BSCS').data['attributes'][0]['combined'], 50.0)
        self.assertEqual(c.patch('/api/departments/computing/', {'directWeight': 101}, format='json').status_code, 400)
        self.assertEqual(self.client_for(self.admin).patch('/api/departments/computing/', {'directWeight': 50}, format='json').status_code, 403)

    def test_po_keeps_direct_and_indirect_separate(self):
        self.offering('C1', 'Fall-2024', {'SP23-BSCS-001': 90})   # GA1 direct 100
        self.upload('alumni', [
            {'program': 'BSCS', 'graduationYear': 2024, 'ratings': {'1': 4, '2': 1}},
            {'program': 'BSCS', 'graduationYear': 2023, 'ratings': {'1': 2, '2': 1}},
        ])
        c = self.client_for(self.qa)
        po = c.get('/api/reports/po-attainment/?programId=BSCS').data['pos'][0]
        self.assertEqual((po['directPercent'], po['directStatus']), (100.0, 'Met'))
        self.assertEqual((po['indirectPercent'], po['indirectStatus']), (25.0, 'Not Met'))    # Q1 50%, Q2 0%
        data = c.get('/api/reports/po-attainment/?programId=BSCS&graduationYear=2024').data
        self.assertEqual(data['pos'][0]['indirectPercent'], 50.0)    # Q1 100%, Q2 0%
        self.assertEqual(data['graduationYears'], [2023, 2024])

    def test_cumulative_file_replaces_only_its_years(self):
        row = lambda year: {'program': 'BSCS', 'year': year, 'batch': 'SP-23', 'ratings': {'1': '5 - Excellent'}}
        self.upload('internship', [row('Summer 2024'), row('Summer 2025')], year=None)
        self.upload('internship', [row('Summer 2026')], year=None)
        r = self.upload('internship', [row('Summer 2025'), row('Summer 2025'), row('Summer 2026')], year=None)
        self.assertEqual((r.data['years'], r.data['replaces']), ({'2025': 2, '2026': 1}, 2))
        years = sorted(SurveyResponse.objects.values_list('year', flat=True))
        self.assertEqual(years, [2024, 2025, 2025, 2026])
        self.assertEqual(SurveyUpload.objects.count(), 2)    # the 2026-only file had nothing left, so it went
        self.assertEqual(SurveyResponse.objects.filter(year=2025).first().period, 'Summer 2025')
        c = self.client_for(self.qa)
        data = c.get('/api/surveys/results/?programId=BSCS&formType=internship').data
        self.assertEqual((data['years'], data['batches'], data['responseCount']), ([2024, 2025, 2026], ['SP23'], 4))
        self.assertEqual(c.get('/api/surveys/results/?programId=BSCS&formType=internship&year=2025').data['responseCount'], 2)
        self.assertEqual(c.get('/api/surveys/results/?programId=BSCS&formType=internship&batch=SP23').data['responseCount'], 4)
        self.assertEqual(c.get('/api/surveys/results/?programId=BSCS&formType=internship&batch=FA22').data['responseCount'], 0)

    def test_row_without_any_year_is_reported(self):
        r = self.upload('exit', [{'program': 'BSCS', 'ratings': {'1': 5}}, {'program': 'BSCS', 'year': '2025', 'ratings': {'1': 5}}], year=None, dryRun=True)
        self.assertEqual((r.data['accepted'], r.data['skipped'], r.data['years']), (1, 1, {'2025': 1}))
        self.assertIn('No year', r.data['errors'][0]['error'])

    def test_new_file_replaces_the_same_form_and_year(self):
        self.assertEqual(self.upload('exit', [{'program': 'BSCS', 'ratings': {'1': 5}}] * 3).status_code, 201)
        r = self.upload('exit', [{'program': 'BSCS', 'ratings': {'1': 5}}])
        self.assertEqual(r.data['replaces'], 3)
        self.assertEqual(SurveyUpload.objects.count(), 1)
        self.assertEqual(SurveyResponse.objects.count(), 1)

    def test_dry_run_saves_nothing_and_bad_rows_are_reported(self):
        r = self.upload('exit', [
            {'program': 'BS Computer Science', 'ratings': {'1': 'Very Good', '2': ''}},
            {'program': 'BBA', 'ratings': {'1': 5}},    # names no programme here: kept as Not specified
            {'program': 'BSCS', 'ratings': {'1': 'maybe'}},
            {'program': 'BSCS', 'ratings': {}},
        ], dryRun=True)
        self.assertEqual((r.data['accepted'], r.data['skipped']), (2, 2))
        self.assertEqual((r.data['programs'], r.data['unrecognizedPrograms']), ({'BSCS': 1, 'Not specified': 1}, {'BBA': 1}))
        self.assertEqual(SurveyUpload.objects.count(), 0)
        self.upload('exit', [{'program': 'BS Computer Science', 'ratings': {'1': 'Very Good', '2': ''}}])
        self.assertEqual(SurveyResponse.objects.get().ratings, {'1': 4})

    def test_mapping_change_leaves_past_results_alone(self):
        self.upload('exit', [{'program': 'BSCS', 'batch': 'SP23', 'ratings': {'1': 5}}])
        c = self.client_for(self.qa)
        r = c.put('/api/surveys/mapping/', {'programId': 'BSCS', 'formType': 'exit', 'mapping': {'1': 'GA-BSCS-2'}}, format='json')
        self.assertEqual(r.status_code, 200)
        results = c.get('/api/surveys/results/?programId=BSCS&formType=exit').data
        self.assertEqual(results['questions'][0]['target'], 'GA-BSCS-1')
        form = next(f for f in c.get('/api/surveys/forms/?programId=BSCS').data['forms'] if f['formType'] == 'exit')
        self.assertEqual(form['questions'][0]['target'], 'GA-BSCS-2')
        self.assertEqual(c.put('/api/surveys/mapping/', {'programId': 'BSCS', 'formType': 'exit', 'mapping': {'1': 'PO9'}}, format='json').status_code, 400)

    def test_students_and_teachers_cannot_see_survey_data(self):
        self.upload('exit', [{'program': 'BSCS', 'ratings': {'1': 5}}])
        paths = ['/api/surveys/forms/?programId=BSCS', '/api/surveys/uploads/', '/api/surveys/results/?programId=BSCS&formType=exit',
                 '/api/reports/cohort-ga/?programId=BSCS', '/api/reports/po-attainment/?programId=BSCS']
        student = User.objects.create(username='s@x.com', email='s@x.com', role='student')
        for user in (student, self.teacher.user):
            for path in paths:
                self.assertEqual(self.client_for(user).get(path).status_code, 403, path)
        for path in paths:
            self.assertEqual(self.client_for(self.admin).get(path).status_code, 200, path)
        # Only QA uploads and changes mappings.
        self.assertEqual(self.client_for(self.admin).post('/api/surveys/uploads/', {}, format='json').status_code, 403)
        self.assertEqual(self.client_for(self.admin).put('/api/surveys/mapping/', {}, format='json').status_code, 403)

    def test_other_department_cannot_read(self):
        other = Department.objects.create(dept_id='biz', name='Business')
        outsider = User.objects.create(username='qa2@x.com', email='qa2@x.com', role='qa')
        QAProfile.objects.create(user=outsider, employee_id='QA2', department=other)
        c = self.client_for(outsider)
        self.assertEqual(c.get('/api/surveys/results/?programId=BSCS&formType=exit').status_code, 404)
        self.assertEqual(c.get('/api/surveys/forms/?programId=BSCS').status_code, 404)

    def test_university_exit_file_and_analysis(self):
        # As in the university's FA22 exit file: short programme names, "Unknown",
        # batches in several layouts, a graduating year column, "." for no comment.
        AdmissionStudent.objects.create(reg_no='FA22-BSCS-001', name='X', email='x@x.com', department=self.dept, program=self.program)
        ai = Program.objects.create(code='BSAI', name='BS Artificial Intelligence', department=self.dept)
        rows = [
            {'program': 'CS', 'batch': 'CS-FA-22', 'graduationYear': 2026, 'ratings': {'1': 4, '2': 2}, 'comment': 'Add more labs.'},
            {'program': 'AI', 'batch': 'Fall 22', 'graduationYear': 2026, 'ratings': {'1': 3, '2': 2}, 'comment': '.'},
            {'program': 'Unknown', 'batch': '2022', 'graduationYear': 2026, 'ratings': {'1': 2, '2': 2}, 'comment': 'No comment'},
            {'program': 'CK', 'batch': 'Fall 2022', 'graduationYear': 2026, 'ratings': {'1': 5, '2': 5}, 'comment': '-'},
            {'program': 'CS', 'batch': 'SP-22', 'graduationYear': 2025, 'ratings': {'1': 5, '2': 4}, 'comment': 'Great faculty overall'},
        ]
        r = self.upload('exit', rows, year=None, defaultBatch='FA22')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data['programs'], r.data['batches']), ({'BSCS': 2, 'BSAI': 1, 'Not specified': 2}, {'FA22': 4, 'SP22': 1}))
        self.assertEqual(r.data['years'], {'2025': 1, '2026': 4})
        data = self.client_for(self.qa).get('/api/surveys/analysis/?formType=exit').data
        self.assertEqual(data['available'], ['SP22', 'FA22'])
        fa22 = data['groups'][1]
        self.assertEqual((fa22['key'], fa22['population']), ('FA22', 1))
        self.assertEqual(fa22['composition'], {'BSCS': 1, 'BSAI': 1, 'Not specified': 2})
        kpi1 = fa22['stats']['kpis'][0]
        self.assertEqual((kpi1['average'], kpi1['percent'], kpi1['achieved']), (3.5, 75.0, True))
        kpi2 = fa22['stats']['kpis'][1]
        self.assertEqual((kpi2['average'], kpi2['achieved']), (2.75, False))    # 1 of 4 rated 3 or above
        self.assertEqual(set(fa22['programs']), {'BSCS', 'BSAI'})
        self.assertEqual(fa22['comments'], [{'program': 'BSCS', 'text': 'Add more labs.'}])
        self.assertEqual(data['consolidated']['responses'], 5)
        only = self.client_for(self.qa).get('/api/surveys/analysis/?formType=exit&groups=sp22').data
        self.assertEqual([g['key'] for g in only['groups']], ['SP22'])
        self.assertEqual(self.client_for(User.objects.create(username='s2@x.com', email='s2@x.com', role='student'))
                         .get('/api/surveys/analysis/?formType=exit').status_code, 403)

    def test_analysis_groups_and_sent_to(self):
        for n in range(1, 5):
            AdmissionStudent.objects.create(reg_no=f'FA22-BSCS-00{n}', name='X', email=f'x{n}@x.com', department=self.dept, program=self.program)
        # Internship: grouped by programme, out of the students of the interns' batches.
        self.upload('internship', [
            {'program': 'BSCS', 'batch': 'FA22', 'year': 2025, 'ratings': {'1': 4}},
            {'program': 'BSCS', 'batch': 'FA22', 'year': 2024, 'ratings': {'1': 2}},
            {'program': 'BBA', 'batch': 'FA22', 'year': 2025, 'ratings': {'1': 5}},
        ], year=None)
        data = self.client_for(self.qa).get('/api/surveys/analysis/?formType=internship').data
        self.assertEqual((data['groupBy'], data['available'], data['years']), ('program', ['BSCS', 'Not specified'], [2024, 2025]))
        bscs = data['groups'][0]
        self.assertEqual((bscs['stats']['responses'], bscs['population'], bscs['composition'], bscs['programs']),
                         (2, 4, {'FA22': 2}, {}))
        y2025 = self.client_for(self.qa).get('/api/surveys/analysis/?formType=internship&year=2025').data
        self.assertEqual([g['stats']['responses'] for g in y2025['groups']], [1, 1])
        # Alumni: out of the graduates of that year (FA22 and SP23 both finish in 2026).
        self.upload('alumni', [{'program': 'BSCS', 'graduationYear': 2026, 'ratings': {'1': 4}}])
        alumni = self.client_for(self.qa).get('/api/surveys/analysis/?formType=alumni').data['groups'][0]
        self.assertEqual((alumni['key'], alumni['population'], alumni['populationSource']), ('2026', 6, 'students'))
        # Employers: nothing to count from, until QA enters how many it was sent to.
        self.upload('employer', [{'program': 'BSCS', 'graduationYear': 2026, 'ratings': {'1': 4}}])
        url = '/api/surveys/analysis/'
        self.assertIsNone(self.client_for(self.qa).get(url + '?formType=employer').data['groups'][0]['population'])
        self.assertEqual(self.client_for(self.admin).put(url, {'formType': 'employer', 'groupKey': '2026', 'count': 12}, format='json').status_code, 403)
        self.assertEqual(self.client_for(self.qa).put(url, {'formType': 'employer', 'groupKey': '2026', 'count': 'x'}, format='json').status_code, 400)
        self.assertEqual(self.client_for(self.qa).put(url, {'formType': 'employer', 'groupKey': '2026', 'count': 12}, format='json').status_code, 200)
        employer = self.client_for(self.admin).get(url + '?formType=employer').data['groups'][0]
        self.assertEqual((employer['population'], employer['populationSource']), (12, 'entered'))
        self.client_for(self.qa).put(url, {'formType': 'employer', 'groupKey': '2026', 'count': ''}, format='json')
        self.assertIsNone(self.client_for(self.qa).get(url + '?formType=employer').data['groups'][0]['population'])

    def test_alumni_report(self):
        # As in the university's BSAI alumni report: PO-04 is 24 of 25 responses rated 3 or above.
        for n in range(1, 6):
            AdmissionStudent.objects.create(reg_no=f'SP22-BSCS-00{n}', name='X', email=f'a{n}@x.com', department=self.dept, program=self.program)
        q12 = [5, 5, 4, 4, 2]
        rows = [{'program': 'BSCS', 'batch': 'CS-SP-2022', 'graduationYear': 2026, 'respondentName': f'Alumnus {i}', 'regNo': f'052-21-{i}',
                 'organization': 'Zaim associate', 'designation': 'Team Lead', 'employmentStatus': status,
                 'ratings': {str(q): (q12[i] if q == 12 else 4) for q in range(1, 14)}}
                for i, status in enumerate(['Employed', 'Currently employed', 'Freelancing', 'Entrepreneur (own business)', 'Unemployed'])]
        self.assertEqual(self.upload('alumni', rows).status_code, 201)
        for no, target in {5: 'PO4', 6: 'PO4', 8: 'PO4', 11: 'PO4', 12: 'PO4', 13: 'PO3'}.items():
            SurveyMapping.objects.update_or_create(program=self.program, form_type='alumni', question_no=no, defaults={'target': target})
        data = self.client_for(self.admin).get('/api/surveys/alumni-report/?programId=bscs').data
        self.assertEqual(data['available'], ['SP22'])
        g = data['groups'][0]
        self.assertEqual((g['responses'], g['population'], g['recipientsKey']), (5, 5, 'BSCS:SP22'))
        self.assertEqual(g['employment'], {'Employed': 2, 'Freelancer': 1, 'Entrepreneur': 1, 'Unemployed': 1})
        q = g['questions'][11]
        self.assertEqual((q['counts'], q['percent']), ({'5': 2, '4': 2, '3': 0, '2': 1, '1': 0}, 80.0))
        po4 = next(p for p in g['pos'] if p['code'] == 'PO4')
        self.assertEqual((po4['score'], po4['attained'], po4['questions']), (96.0, True, [5, 6, 8, 11, 12]))
        self.assertEqual(g['students'][0]['organization'], 'Zaim associate')
        self.client_for(self.qa).put('/api/surveys/analysis/', {'formType': 'alumni', 'groupKey': 'BSCS:SP22', 'count': 8}, format='json')
        self.assertEqual(self.client_for(self.qa).get('/api/surveys/alumni-report/?programId=bscs').data['groups'][0]['population'], 8)
        self.assertEqual(self.client_for(self.teacher.user).get('/api/surveys/alumni-report/?programId=bscs').status_code, 403)

    def test_parsers(self):
        self.assertEqual([parse_rating(v) for v in (5, '5', '4.0', '3 = Good', 'Excellent', 'very good', '', None)],
                         [5, 5, 4, 3, 5, 4, None, None])
        for bad in ('6', 'maybe', '0'):
            with self.assertRaises(ValueError):
                parse_rating(bad)
        self.assertEqual([parse_year(v) for v in (2026, '2025', 'Summer 2026', 'Fall-2025', 'none', '12026', None)],
                         [2026, 2025, 2026, 2025, None, None, None])
        self.assertEqual([batch_code(v) for v in ('CS-SP-23', 'SP23-BSCS-001', '052-FA23-22144', 'sp 2024', 'none',
                                                  'Fall 22', 'Fall 2022', 'SE-FA-22', 'Ck-FA-22', '2022', 'Spring-2023')],
                         ['SP23', 'SP23', 'FA23', 'SP24', '', 'FA22', 'FA22', 'FA22', 'FA22', '', 'SP23'])
        self.assertEqual([meaningful_comment(v) for v in ('.', '-', '/', 'No comment', 'All is good.', 'Deal students Politely', '')],
                         [False, False, False, False, True, True, False])
