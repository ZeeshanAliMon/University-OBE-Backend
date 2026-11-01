from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from core.models import (
    User, Department, Program, Course, InstructorProfile,
    CourseAssignment, MarksCategory, UnitItem,
)
from core.views import InstructorCourseView


class InstructorCourseCategoriesRegressionTest(TestCase):
    """
    Regression test for: AttributeError - Cannot find 'categories' on
    InstructorCourse object, 'categories__unit_items__questions' is an
    invalid parameter to prefetch_related().

    MarksCategory.course was repointed from InstructorCourse to Course
    (migration 0011) so marking structures are shared across every
    instructor/term teaching the same catalog course. This broke the
    InstructorCourseView GET endpoint, which still assumed a direct
    'categories' relation on InstructorCourse. Fixed by adding
    InstructorCourse.catalog_course and routing category/unit access
    through it everywhere (views.prefetch_instructor_course,
    InstructorCourseSerializer.get_categories/get_unitsData, the POST
    sync handler, the student dashboard endpoint, and the close-course
    validation gate).
    """

    def setUp(self):
        self.dept = Department.objects.create(dept_id='CS', name='Computer Science')
        self.program = Program.objects.create(code='CS', name='Computer Science', department=self.dept)
        self.course = Course.objects.create(
            code='CS12', title='Course Ali', department=self.dept,
            program=self.program, credit_hours=3,
        )
        cat = MarksCategory.objects.create(
            course=self.course, name='Assignment', percentage=30, units=1, order=0
        )
        UnitItem.objects.create(category=cat, unit_no=1, total_marks=10, weightage=100, passing=5)

        self.user = User.objects.create(
            username='teacher@mon.com', email='teacher@mon.com', role='instructor'
        )
        self.profile = InstructorProfile.objects.create(
            user=self.user, employee_id='TEAHCS', designation='Lecturer', department=self.dept
        )
        CourseAssignment.objects.create(
            instructor=self.profile, course=self.course, program=self.program,
            academic_year='Fall-2026',
        )
        self.factory = APIRequestFactory()
        self.view = InstructorCourseView.as_view()

    def test_get_does_not_raise_and_includes_categories(self):
        request = self.factory.get('/api/instructor/courses/')
        force_authenticate(request, user=self.user)
        request.user = self.user

        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        ic_data = response.data[0]
        self.assertEqual(ic_data['categories'][0]['name'], 'Assignment')
        self.assertIn('Assignment', ic_data['unitsData'])
        self.assertEqual(ic_data['unitsData']['Assignment'][0]['totalMarks'], 10)

    def test_post_sync_persists_categories_via_catalog_course(self):
        payload = {
            "courses": [{
                "id": "course-new-SE10-TEAHCS-cs",
                "code": "SE10",
                "title": "Software Design",
                "courseType": "Theory",
                "departmentId": "CS",
                "programId": "cs",
                "creditHours": 3,
                "cloCount": 4,
                "academicYear": "Fall-2026",
                "selectedGradingSystem": "ready1",
                "customGradingSystem": [],
                "categories": [{"name": "Quiz", "percentage": 100, "units": 1}],
                "unitsData": {
                    "Quiz": [{"unitNo": 1, "passing": 5, "totalMarks": 10, "weightage": 100, "mappedCLOs": []}]
                },
                "students": [],
                "obeQuestions": [],
            }]
        }
        request = self.factory.post('/api/instructor/courses/', payload, format='json')
        force_authenticate(request, user=self.user)
        request.user = self.user

        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        saved = response.data[0]
        self.assertEqual(saved['categories'][0]['name'], 'Quiz')
        self.assertEqual(saved['unitsData']['Quiz'][0]['totalMarks'], 10)


class AuditRegressionTests(TestCase):
    """
    Regressions from the code audit: roster syncs must never delete marks,
    an older copy of a course must not overwrite newer marks, teachers see
    their latest term by date, GA reports use questions passed, and the
    smaller fixes (CLO ownership, per-term unassign, custom grade ranges,
    marks in omitted categories).
    """

    def setUp(self):
        from core.models import (
            InstructorCourse, CourseStudent, StudentMark, OBEQuestion,
            OBEStudentMark, CLO, GraduateAttribute, DeptAdminProfile,
        )
        self.dept = Department.objects.create(dept_id='CS', name='Computer Science')
        self.program = Program.objects.create(code='CS', name='Computer Science', department=self.dept)
        self.course = Course.objects.create(code='CS12', title='Course', department=self.dept,
                                            program=self.program, credit_hours=3)
        self.cat = MarksCategory.objects.create(course=self.course, name='Quiz', percentage=100, units=1, order=0)
        self.unit = UnitItem.objects.create(category=self.cat, unit_no=1, total_marks=10, weightage=100, passing=5)
        self.ua = User.objects.create(username='a@x.com', email='a@x.com', role='instructor')
        self.pa = InstructorProfile.objects.create(user=self.ua, employee_id='EA', department=self.dept)
        self.ub = User.objects.create(username='b@x.com', email='b@x.com', role='instructor')
        InstructorProfile.objects.create(user=self.ub, employee_id='EB', department=self.dept)
        self.ic = InstructorCourse.objects.create(
            frontend_id='ic-a', instructor=self.pa, code='CS12', title='Course',
            department=self.dept, program=self.program, catalog_course=self.course,
            academic_year='Fall-2024',
        )
        self.qa = User.objects.create(username='qa@x.com', email='qa@x.com', role='qa')
        self.da = User.objects.create(username='da@x.com', email='da@x.com', role='dept_admin')
        DeptAdminProfile.objects.create(user=self.da, employee_id='DA1', department=self.dept)
        self.ga = GraduateAttribute.objects.create(ga_id='CS1', name='Knowledge', department=self.dept, program=self.program)
        CLO.objects.create(course=self.ic, code='CLO-1', mapped_ga=self.ga, order=1)
        self.q = OBEQuestion.objects.create(course=self.ic, unit_item=self.unit, frontend_id='q1', category_name='Quiz',
                                            unit_no=1, question_name='Q1', max_marks=10, mapped_clos=['CLO-1'])
        # R1 passed the GA question (8/10), R2 failed it (2/10), R3 has no marks at all.
        self.r1 = CourseStudent.objects.create(course=self.ic, reg_no='R1', name='One')
        self.r2 = CourseStudent.objects.create(course=self.ic, reg_no='R2', name='Two')
        self.r3 = CourseStudent.objects.create(course=self.ic, reg_no='R3', name='Three')
        StudentMark.objects.create(student=self.r1, unit_item=self.unit, score=8)
        OBEStudentMark.objects.create(student=self.r1, question=self.q, score=8)
        OBEStudentMark.objects.create(student=self.r2, question=self.q, score=2)
        self.CourseStudent = CourseStudent

    def client_for(self, user):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def roster(self):
        return sorted(self.CourseStudent.objects.filter(course=self.ic).values_list('reg_no', flat=True))

    # ── Roster syncs never delete marks ──────────────────────────────────────
    def test_empty_roster_sync_keeps_students_with_marks(self):
        r = self.client_for(self.da).post('/api/admin/enroll/', {'courseId': 'ic-a', 'students': []}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.roster(), ['R1', 'R2'])          # R3 had no marks -> removed
        self.assertEqual(sorted(r.data['kept']), ['R1', 'R2'])

    def test_roster_sync_matches_reg_no_ignoring_case_and_spaces(self):
        r = self.client_for(self.da).post('/api/admin/enroll/', {'courseId': 'ic-a', 'students': [
            {'regNo': ' r1 ', 'name': 'One'}, {'regNo': 'r2', 'name': 'Two'}, {'regNo': 'R3', 'name': 'Three'}]},
            format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.roster(), ['R1', 'R2', 'R3'])     # no duplicates, nothing deleted
        self.assertEqual(r.data['enrolled'], [])

    def test_single_unenroll_refuses_student_with_marks(self):
        c = self.client_for(self.da)
        self.assertEqual(c.delete('/api/admin/enroll/', {'courseId': 'ic-a', 'regNo': 'r1'}, format='json').status_code, 400)
        self.assertEqual(c.delete('/api/admin/enroll/', {'courseId': 'ic-a', 'regNo': 'r3'}, format='json').status_code, 204)
        self.assertEqual(self.roster(), ['R1', 'R2'])

    # ── An older copy can't overwrite newer marks ────────────────────────────
    def _save(self, version, mark):
        payload = {'courses': [{
            'id': 'ic-a', 'code': 'CS12', 'title': 'Course', 'courseType': 'Theory',
            'departmentId': 'CS', 'programId': 'cs', 'academicYear': 'Fall-2024',
            'selectedGradingSystem': 'ready1', 'customGradingSystem': [],
            'categories': [{'name': 'Quiz', 'percentage': 100, 'units': 1}],
            'unitsData': {'Quiz': [{'unitNo': 1, 'passing': 5, 'totalMarks': 10, 'weightage': 100, 'mappedCLOs': []}]},
            'students': [{'regNo': 'R1', 'name': 'One', 'marks': {'Quiz-1': mark}}],
            'obeQuestions': [{'id': 'q1', 'categoryName': 'Quiz', 'unitNo': 1, 'questionName': 'Q1',
                              'maxMarks': 10, 'mappedCLOs': ['CLO-1']}],
        }]}
        if version:
            payload['courses'][0]['updatedAt'] = version
        return self.client_for(self.ua).post('/api/instructor/courses/', payload, format='json')

    def test_stale_save_is_refused_and_current_save_accepted(self):
        old_version = self.client_for(self.ua).get('/api/instructor/courses/').data[0]['updatedAt']
        first = self._save(old_version, 9)                     # tab A saves with the current version
        self.assertEqual(first.status_code, 200, first.content)
        stale = self._save(old_version, 1)                     # tab B still holds the old version
        self.assertEqual(stale.status_code, 400, stale.content)
        self.assertTrue(stale.data['errors'][0].get('stale'))
        self.assertEqual(self.r1.marks.get(unit_item=self.unit).score, 9)
        again = self._save(first.data[0]['updatedAt'], 7)      # tab A again, with the version it got back
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(self.r1.marks.get(unit_item=self.unit).score, 7)

    # ── Teachers see what they haven't handed in, whatever the term ──────────
    def test_teacher_keeps_unsubmitted_course_when_new_term_starts(self):
        from core.models import InstructorCourse
        InstructorCourse.objects.create(
            frontend_id='ic-new', instructor=self.pa, code='CS12', title='Course',
            department=self.dept, program=self.program, catalog_course=self.course,
            academic_year='Spring-2025',
        )
        r = self.client_for(self.ua).get('/api/instructor/courses/')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual({c['academicYear'] for c in r.data}, {'Fall-2024', 'Spring-2025'})

    # ── Submitting final marks ───────────────────────────────────────────────
    def _mark_absent(self, reg_no='R3', result_status='absent'):
        return self.client_for(self.ua).patch('/api/instructor/courses/ic-a/student-status/',
                                              {'regNo': reg_no, 'resultStatus': result_status}, format='json')

    def _submit(self, **body):
        return self.client_for(self.ua).post('/api/instructor/courses/ic-a/submit/', body, format='json')

    def _second_quiz(self):
        """Course now sets 2 quizzes; returns the second one's unit."""
        self.cat.units = 2
        self.cat.save()
        self.unit.weightage = 50
        self.unit.save()
        return UnitItem.objects.create(category=self.cat, unit_no=2, total_marks=10, weightage=50, passing=5)

    def test_missing_mark_blocks_until_student_marked_absent(self):
        r = self._submit()
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(r.data['missing'], [{'regNo': 'R3', 'name': 'Three', 'items': ['Quiz 1']}])
        self.assertEqual(self._mark_absent().status_code, 200)
        self.assertEqual(self._submit().status_code, 200)

    def test_quiz_nobody_was_marked_in_warns_and_can_be_accepted(self):
        self._second_quiz()
        self._mark_absent()
        c = self.client_for(self.ua)
        check = c.get('/api/instructor/courses/ic-a/submit/').data
        self.assertEqual(check['missing'], [])
        self.assertEqual(len(check['warnings']), 1)
        self.assertIn('Quiz 2', check['warnings'][0])
        self.assertEqual(self._submit().status_code, 409)                    # not accepted yet
        self.assertEqual(self._submit(acknowledgeWarnings=True).status_code, 200)
        self.ic.refresh_from_db()
        self.assertIn('Quiz 2', self.ic.submission_warnings[0])

    def test_student_missing_one_quiz_others_have_blocks(self):
        from core.models import StudentMark
        quiz2 = self._second_quiz()
        self._mark_absent()
        StudentMark.objects.create(student=self.r1, unit_item=quiz2, score=7)
        check = self.client_for(self.ua).get('/api/instructor/courses/ic-a/submit/').data
        self.assertEqual(check['warnings'], [])
        self.assertEqual(check['missing'], [{'regNo': 'R2', 'name': 'Two', 'items': ['Quiz 2']}])

    def test_all_zero_quiz_counts_as_not_marked(self):
        from core.models import StudentMark
        quiz2 = self._second_quiz()
        self._mark_absent()
        for s in (self.r1, self.r2):
            StudentMark.objects.create(student=s, unit_item=quiz2, score=0)
        check = self.client_for(self.ua).get('/api/instructor/courses/ic-a/submit/').data
        self.assertEqual(len(check['warnings']), 1)

    def _save_question_mark(self, reg_no, score):
        payload = {'courses': [{
            'id': 'ic-a', 'code': 'CS12', 'title': 'Course', 'courseType': 'Theory',
            'departmentId': 'CS', 'programId': 'cs', 'academicYear': 'Fall-2024',
            'categories': [{'name': 'Quiz', 'percentage': 100, 'units': 1}],
            'unitsData': {'Quiz': [{'unitNo': 1, 'passing': 5, 'totalMarks': 10, 'weightage': 100, 'mappedCLOs': []}]},
            'students': [],
            'obeQuestions': [{'id': 'q1', 'categoryName': 'Quiz', 'unitNo': 1, 'questionName': 'Q1',
                              'maxMarks': 10, 'mappedCLOs': ['CLO-1']}],
            'obeMarks': {reg_no: {'q1': score}},
        }]}
        return self.client_for(self.ua).post('/api/instructor/courses/', payload, format='json')

    def test_cleared_cell_removes_the_mark_and_blocks_submitting(self):
        from core.models import OBEStudentMark
        self.assertEqual(self._save_question_mark('R2', None).status_code, 200)
        self.assertFalse(OBEStudentMark.objects.filter(student=self.r2).exists())
        self.assertTrue(OBEStudentMark.objects.filter(student=self.r1).exists())     # others untouched
        self._mark_absent()
        check = self.client_for(self.ua).get('/api/instructor/courses/ic-a/submit/').data
        self.assertEqual(check['missing'], [{'regNo': 'R2', 'name': 'Two', 'items': ['Quiz 1']}])

    def test_typed_zero_is_a_real_mark(self):
        self.assertEqual(self._save_question_mark('R3', 0).status_code, 200)
        self.assertEqual(self.r3.obe_marks.get(question=self.q).score, 0)
        check = self.client_for(self.ua).get('/api/instructor/courses/ic-a/submit/').data
        self.assertEqual(check['missing'], [])

    def test_submitted_course_is_read_only_and_moves_to_past_courses(self):
        self._mark_absent()
        self.assertEqual(self._submit().status_code, 200)
        c = self.client_for(self.ua)
        self.assertEqual(c.get('/api/instructor/courses/').data, [])
        past = c.get('/api/instructor/past-courses/').data
        self.assertEqual([(p['id'], p['state']) for p in past], [('ic-a', 'submitted')])
        self.assertEqual({s['regNo']: s['grade'] for s in past[0]['students']}['R1'], self._grade_of_r1())
        # Every way a teacher could still change it is refused.
        self.assertEqual(self._save(None, 1).status_code, 400)
        self.assertEqual(self.r1.marks.get(unit_item=self.unit).score, 8)
        self.assertEqual(self._mark_absent('R2').status_code, 400)
        self.assertEqual(self._submit().status_code, 400)
        self.assertEqual(c.post('/api/instructor/courses/ic-a/students/',
                                {'students': [{'regNo': 'R9', 'name': 'Nine'}]}, format='json').status_code, 400)
        self.assertEqual(c.post('/api/instructor/courses/ic-a/clos/', {'code': 'CLO-9'}, format='json').status_code, 400)
        self.assertEqual(c.delete('/api/instructor/courses/ic-a/').status_code, 400)
        # The admin can't change the roster under it either.
        self.assertEqual(self.client_for(self.da).post('/api/admin/enroll/', {'courseId': 'ic-a', 'students': []},
                                                       format='json').status_code, 400)

    def test_past_course_detail_has_everything_but_only_once_handed_in(self):
        c = self.client_for(self.ua)
        url = '/api/instructor/past-courses/ic-a/'
        self.assertEqual(c.get(url).status_code, 404)                        # still a current course
        self._mark_absent()
        self._submit()
        data = c.get(url).data
        self.assertEqual(data['code'], 'CS12')
        self.assertEqual(data['categories'][0]['name'], 'Quiz')
        self.assertEqual(data['obeMarks']['R1'], {'q1': 8})
        self.assertEqual(data['clos'][0]['code'], 'CLO-1')
        self.assertIsNotNone(data['submittedAt'])
        self.assertEqual(self.client_for(self.ub).get(url).status_code, 404)  # another teacher's

    def _grade_of_r1(self):
        from core.views import _get_grade, _sheet_course_total
        return _get_grade(_sheet_course_total(self.r1)['total'], self.ic)[0]

    def test_other_teacher_cannot_submit(self):
        c = self.client_for(self.ub)
        self.assertEqual(c.post('/api/instructor/courses/ic-a/submit/', {}, format='json').status_code, 404)
        self.assertEqual(c.patch('/api/instructor/courses/ic-a/student-status/',
                                 {'regNo': 'R3', 'resultStatus': 'absent'}, format='json').status_code, 404)

    def test_admin_sends_back_with_note_and_teacher_can_edit_again(self):
        self._mark_absent()
        self._submit()
        admin = self.client_for(self.da)
        self.assertEqual(admin.post('/api/admin/return-course/', {'courseId': 'ic-a'}, format='json').status_code, 400)
        r = admin.post('/api/admin/return-course/', {'courseId': 'ic-a', 'note': 'Quiz 1 looks wrong'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        teacher = self.client_for(self.ua).get('/api/instructor/courses/').data
        self.assertEqual(teacher[0]['returnNote'], 'Quiz 1 looks wrong')
        self.assertIsNone(teacher[0]['submittedAt'])
        self.assertEqual(self._save(teacher[0]['updatedAt'], 9).status_code, 200)
        self.assertEqual(self._submit().status_code, 200)
        self.ic.refresh_from_db()
        self.assertEqual(self.ic.return_note, '')

    def test_other_department_admin_cannot_send_back(self):
        from core.models import DeptAdminProfile
        other = Department.objects.create(dept_id='EE', name='Electrical')
        u = User.objects.create(username='ee@x.com', email='ee@x.com', role='dept_admin')
        DeptAdminProfile.objects.create(user=u, employee_id='DA2', department=other)
        self._mark_absent()
        self._submit()
        r = self.client_for(u).post('/api/admin/return-course/', {'courseId': 'ic-a', 'note': 'x'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_finalize_without_submission_needs_explicit_override(self):
        admin = self.client_for(self.da)
        r = admin.post('/api/admin/finalize-course/', {'courseId': 'ic-a'}, format='json')
        self.assertEqual(r.status_code, 409, r.content)
        self.assertEqual(r.data['code'], 'not_submitted')
        self.ic.refresh_from_db()
        self.assertEqual(self.ic.status, 'active')
        r = admin.post('/api/admin/finalize-course/', {'courseId': 'ic-a', 'overrideNotSubmitted': True}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.client_for(self.ua).get('/api/instructor/past-courses/').data[0]['state'], 'finalized')

    def test_finalized_course_cannot_be_sent_back(self):
        self._mark_absent()
        self._submit()
        admin = self.client_for(self.da)
        self.assertEqual(admin.post('/api/admin/finalize-course/', {'courseId': 'ic-a'}, format='json').status_code, 200)
        r = admin.post('/api/admin/return-course/', {'courseId': 'ic-a', 'note': 'x'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_withdrawn_student_gets_w_and_leaves_gpa_and_reports(self):
        from core.models import FinalResult, Student
        self._mark_absent('R2', 'withdrawn')
        self._mark_absent('R3', 'absent')
        self.assertEqual(self._submit().status_code, 200)
        # R1 passed, R3 absent with no marks is skipped, R2 withdrawn is out -> 100%, not 50%.
        ga = self.client_for(self.qa).get('/api/reports/program-ga-attainment/?programId=cs').data['attributes'][0]
        self.assertEqual(ga['averageAttainment'], 100.0)
        attainment = self.client_for(self.qa).get('/api/reports/course-attainment/?courseCode=CS12&programId=cs').data
        self.assertEqual(attainment['classSize'], 2)                         # R1 and R3

        self.assertEqual(self.client_for(self.da).post('/api/admin/finalize-course/', {'courseId': 'ic-a'},
                                                       format='json').status_code, 200)
        w = FinalResult.objects.get(student_reg_no='R2')
        self.assertEqual((w.grade_letter, w.grade_points, w.clo_attainments), ('W', 0.0, []))
        self.assertEqual(FinalResult.objects.get(student_reg_no='R3').grade_letter, 'F')

        su = User.objects.create(username='r2@x.com', email='r2@x.com', role='student')
        Student.objects.create(user=su, reg_no='R2', program=self.program, department=self.dept)
        courses = self.client_for(su).get('/api/student/courses/').data
        self.assertEqual(courses[0]['grade'], 'W')

    # ── GA reports use questions passed and skip unmarked students ───────────
    def test_program_ga_uses_questions_passed_and_skips_unmarked(self):
        r = self.client_for(self.qa).get('/api/reports/program-ga-attainment/?programId=cs')
        self.assertEqual(r.status_code, 200, r.content)
        ga = [a for a in r.data['attributes'] if a['id'] == 'CS1'][0]
        # R1 passed (100%), R2 failed (0%); R3 has no marks and is left out -> 50%, not 33.3%
        self.assertEqual(ga['averageAttainment'], 50.0)
        self.assertEqual(ga['contributingCourses'][0]['code'], 'CS12')

    def test_student_courses_include_ga_by_questions(self):
        from core.models import Student
        su = User.objects.create(username='s@x.com', email='s@x.com', role='student')
        Student.objects.create(user=su, reg_no='R1', program=self.program, department=self.dept)
        r = self.client_for(su).get('/api/student/courses/')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data[0]['gaAttainments'],
                         [{'gaId': 'CS1', 'gaTitle': 'Knowledge', 'passed': 1, 'total': 1, 'percent': 100.0, 'attained': True}])

    # ── CLO CQI gets the semester from the plan ──────────────────────────────
    def test_clo_cqi_semester_comes_from_plan(self):
        from core.models import SemesterPlan
        SemesterPlan.objects.create(program=self.program, semester='3rd', course_codes=['CS12'])
        c = self.client_for(self.qa)
        url = '/api/reports/clo-cqi/?departmentId=CS&programId=cs'
        self.assertEqual(c.get(url).data['courses'][0]['semester'], '3rd')
        self.assertEqual(len(c.get(url + '&semester=3rd').data['courses']), 1)
        self.assertEqual(c.get(url + '&semester=1st').data['courses'], [])

    # ── Reports hold up on realistic data ────────────────────────────────────
    def test_program_wide_views_survive_many_questions(self):
        # SQLite refused the marks -> question prefetch once it spanned this many questions.
        from core.models import OBEQuestion, OBEStudentMark
        qs = OBEQuestion.objects.bulk_create([
            OBEQuestion(course=self.ic, unit_item=self.unit, frontend_id=f'bulk{i}', category_name='Quiz',
                        unit_no=1, question_name=f'Q{i}', max_marks=10, mapped_clos=['CLO-1'])
            for i in range(1200)
        ])
        OBEStudentMark.objects.bulk_create([OBEStudentMark(student=self.r1, question=q, score=5) for q in qs])
        c = self.client_for(self.qa)
        for url in ['/api/instructor/courses/', '/api/reports/co-attainment-summary/?programId=cs',
                    '/api/reports/at-risk-students/?programId=cs', '/api/reports/course-attainment/?courseCode=CS12']:
            self.assertEqual(c.get(url).status_code, 200, url)

    def test_co_summary_and_at_risk_take_the_semester_from_the_plan(self):
        from core.models import SemesterPlan
        SemesterPlan.objects.create(program=self.program, semester='3rd', course_codes=['CS12'])
        c = self.client_for(self.qa)
        co = '/api/reports/co-attainment-summary/?programId=cs'
        self.assertEqual(len(c.get(co + '&semester=3rd').data['courses']), 1)
        self.assertEqual(c.get(co + '&semester=1st').data['courses'], [])
        risk = '/api/reports/at-risk-students/?programId=cs'
        self.r2.obe_marks.update(score=0)
        from core.models import CLO, OBEQuestion, OBEStudentMark
        CLO.objects.create(course=self.ic, code='CLO-2', mapped_ga=self.ga, order=2)
        q2 = OBEQuestion.objects.create(course=self.ic, unit_item=self.unit, frontend_id='q2', category_name='Quiz',
                                        unit_no=1, question_name='Q2', max_marks=10, mapped_clos=['CLO-2'])
        OBEStudentMark.objects.create(student=self.r2, question=q2, score=0)
        self.assertIn('R2', [s['regNo'] for s in c.get(risk + '&semester=3rd').data['students']])
        self.assertEqual(c.get(risk + '&semester=1st').data['students'], [])

    def test_gap_analysis_leaves_out_other_programs_gas(self):
        from core.models import GraduateAttribute
        other = Program.objects.create(code='AI', name='AI', department=self.dept)
        GraduateAttribute.objects.create(ga_id='AI1', name='Other', department=self.dept, program=other)
        GraduateAttribute.objects.create(ga_id='ALL1', name='Shared', department=self.dept)
        r = self.client_for(self.qa).get('/api/reports/gap-analysis/?programId=cs')
        self.assertEqual(sorted(a['gaId'] for a in r.data['attributes']), ['ALL1', 'CS1'])

    # ── Semester comes from the reg number and the date ──────────────────────
    def test_semester_from_reg_no(self):
        import datetime
        from core.models import semester_from_reg_no as sem
        fall_2026 = datetime.date(2026, 11, 1)
        self.assertEqual(sem('22144-SP23', fall_2026), '8th')
        self.assertEqual(sem('052-SP23-22144', fall_2026), '8th')
        self.assertEqual(sem('FA23-BSCS-001', fall_2026), '7th')
        self.assertEqual(sem('22144-sp26', fall_2026), '2nd')
        self.assertEqual(sem('22144-FA26', fall_2026), '1st')
        self.assertEqual(sem('22144-SP20', fall_2026), '8th')    # never past 8th
        self.assertEqual(sem('22144-SP27', fall_2026), '1st')    # admitted early
        self.assertEqual(sem('22144-FA26', datetime.date(2027, 1, 31)), '1st')   # January is still Fall
        self.assertEqual(sem('22144-FA26', datetime.date(2027, 2, 1)), '2nd')
        self.assertIsNone(sem('R1', fall_2026))

    def test_login_and_student_list_use_the_calculated_semester(self):
        import datetime
        from unittest import mock
        from core.models import AdmissionStudent, Student
        AdmissionStudent.objects.create(reg_no='22144-SP23', name='A', email='a1@x.com', department=self.dept,
                                        program=self.program, batch='Spring', semester='1st')
        AdmissionStudent.objects.create(reg_no='ROLL7', name='B', email='b1@x.com', department=self.dept,
                                        program=self.program, batch='Fall', semester='3rd')
        su = User.objects.create(username='a1@x.com', email='a1@x.com', role='student')
        su.set_password('secret-pass-1')
        su.save()
        Student.objects.create(user=su, reg_no='22144-SP23', program=self.program, department=self.dept)
        with mock.patch('core.models.timezone.localdate', return_value=datetime.date(2026, 11, 1)):
            rows = {s['regNo']: s['semester'] for s in self.client_for(self.qa).get('/api/students/').data}
            login = self.client_for(self.qa).post('/api/auth/login/', {'email': 'a1@x.com', 'password': 'secret-pass-1'}, format='json')
        self.assertEqual(rows, {'22144-SP23': '8th', 'ROLL7': '3rd'})     # no batch: the saved one
        self.assertEqual(login.data['user']['semester'], '8th')

    def test_batch_report_finds_batch_at_end_of_reg_no(self):
        from core.models import AdmissionStudent
        AdmissionStudent.objects.create(reg_no='22144-SP23', name='A', email='a2@x.com', department=self.dept,
                                        program=self.program, batch='Spring')
        AdmissionStudent.objects.create(reg_no='22145-FA23', name='B', email='b2@x.com', department=self.dept,
                                        program=self.program, batch='Fall')
        r = self.client_for(self.qa).get('/api/reports/batch-ga-attainment/?batch=sp23&departmentId=CS')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['studentCount'], 1)

    # ── Smaller audit fixes ──────────────────────────────────────────────────
    def test_other_instructor_cannot_touch_clos(self):
        b = self.client_for(self.ub)
        self.assertEqual(b.get('/api/instructor/courses/ic-a/clos/').status_code, 404)
        self.assertEqual(self.client_for(self.ua).get('/api/instructor/courses/ic-a/clos/').status_code, 200)

    def test_unassign_removes_only_that_term(self):
        CourseAssignment.objects.create(instructor=self.pa, course=self.course, program=self.program, academic_year='Fall-2025')
        CourseAssignment.objects.create(instructor=self.pa, course=self.course, program=self.program, academic_year='Spring-2026')
        r = self.client_for(self.da).delete('/api/admin/course-assignments/', {
            'teacherId': 'EA', 'courseCode': 'CS12', 'programId': 'cs', 'academicYear': 'Fall-2025'}, format='json')
        self.assertEqual(r.status_code, 204, r.content)
        self.assertEqual(list(CourseAssignment.objects.values_list('academic_year', flat=True)), ['Spring-2026'])

    def test_custom_grade_percentage_comes_back_as_range(self):
        from core.models import GradeScale
        for i, (g, m) in enumerate([('A', 88), ('B+', 81), ('F', 0)]):
            GradeScale.objects.create(course=self.ic, grade=g, min_percentage=m, points=4 - i, order=i)
        data = self.client_for(self.ua).get('/api/instructor/courses/').data
        tiers = {t['grade']: t['percentage'] for t in data[0]['customGradingSystem']}
        self.assertEqual(tiers, {'A': '88% - 100%', 'B+': '81% - 87%', 'F': 'Below 81%'})

    def test_marks_in_omitted_category_survive_save(self):
        from core.models import StudentMark
        project = MarksCategory.objects.create(course=self.course, name='Project', percentage=20, units=1, order=1)
        punit = UnitItem.objects.create(category=project, unit_no=1, total_marks=10, weightage=100, passing=5)
        StudentMark.objects.create(student=self.r1, unit_item=punit, score=6)
        self.assertEqual(self._save(None, 9).status_code, 200)
        self.assertTrue(StudentMark.objects.filter(student=self.r1, unit_item=punit, score=6).exists())
