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
