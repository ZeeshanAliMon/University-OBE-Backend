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

    # ── Teachers see their latest term by date ───────────────────────────────
    def test_teacher_sees_latest_term_by_date_not_alphabetically(self):
        from core.models import InstructorCourse
        InstructorCourse.objects.create(
            frontend_id='ic-old', instructor=self.pa, code='CS12', title='Course',
            department=self.dept, program=self.program, catalog_course=self.course,
            academic_year='Spring-2023',
        )
        r = self.client_for(self.ua).get('/api/instructor/courses/')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual({c['academicYear'] for c in r.data}, {'Fall-2024'})

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
