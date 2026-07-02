from django.urls import path
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.views import TokenRefreshView


@csrf_exempt
def health_check(request):
    """
    GET /api/health/
    Lightweight, unauthenticated liveness probe for frontend connectivity checks.
    Deliberately does not touch the database — this needs to answer even if the
    DB is having problems, so the frontend can distinguish "server is down" from
    "server is up but degraded".
    """
    return JsonResponse({'status': 'ok'})

from .views import (
    LoginView,
    DepartmentListView, DepartmentDetailView,
    ProgramListView, ProgramDetailView,
    GraduateAttributeListView,
    CourseListView, CourseDetailView,
    InstructorProfileView,
    InstructorCourseView,
    TeacherListView,
    TeacherOnboardingView,
    ChangePasswordView,
    CourseAssignmentView,
    StudentEnrollmentView,
    FinalizeCourseView,
    FinalResultsView,
    SemesterPlanView,
    StudentCoursesView,
    AdmissionStudentListView, AdmissionStudentDetailView,
    CLOListView, CLODetailView,
    DeptAdminProfileView,
    # Reports
    ProgramGAAttainmentView,
    StudentGAAttainmentView,
    CourseAttainmentView,
    StudentSummaryView,
)

urlpatterns = [
    path('health/', health_check, name='health_check'),

    path('auth/login/',         LoginView.as_view(),        name='login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    path('departments/',            DepartmentListView.as_view(),   name='department_list'),
    path('departments/<str:slug>/', DepartmentDetailView.as_view(), name='department_detail'),

    path('programs/',            ProgramListView.as_view(),   name='program_list'),
    path('programs/<str:slug>/', ProgramDetailView.as_view(), name='program_detail'),

    path('gas/', GraduateAttributeListView.as_view(), name='ga_list'),

    path('courses/',            CourseListView.as_view(),   name='course_list'),
    path('courses/<str:slug>/', CourseDetailView.as_view(), name='course_detail'),

    path('instructor/profile/', InstructorProfileView.as_view(), name='instructor_profile'),
    path('instructor/courses/', InstructorCourseView.as_view(),  name='instructor_courses'),

    # CLO management per instructor course
    path('instructor/courses/<str:frontend_id>/clos/',           CLOListView.as_view(),   name='clo_list'),
    path('instructor/courses/<str:frontend_id>/clos/<int:clo_id>/', CLODetailView.as_view(), name='clo_detail'),

    path('teachers/',                          TeacherListView.as_view(),          name='teacher_list'),
    path('admin/teachers/',                    TeacherOnboardingView.as_view(),    name='teacher_onboard'),
    path('admin/teachers/<str:employee_id>/',  TeacherOnboardingView.as_view(),    name='teacher_delete'),
    path('auth/change-password/',              ChangePasswordView.as_view(),       name='change_password'),
    path('admin/course-assignments/', CourseAssignmentView.as_view(), name='course_assignments'),
    path('admin/enroll/',             StudentEnrollmentView.as_view(), name='student_enrollment'),
    path('admin/finalize-course/',    FinalizeCourseView.as_view(),    name='finalize_course'),
    path('reports/final-results/',    FinalResultsView.as_view(),      name='final_results'),
    path('admin/semester-plans/',     SemesterPlanView.as_view(),     name='semester_plans'),

    path('student/courses/', StudentCoursesView.as_view(), name='student_courses'),

    path('students/',              AdmissionStudentListView.as_view(),   name='student_list'),
    path('students/<str:reg_no>/', AdmissionStudentDetailView.as_view(), name='student_detail'),

    path('admin/profile/', DeptAdminProfileView.as_view(), name='dept_admin_profile'),

    # Reports
    path('reports/program-ga-attainment/', ProgramGAAttainmentView.as_view(),  name='report_program_ga'),
    path('reports/student-ga-attainment/', StudentGAAttainmentView.as_view(),  name='report_student_ga'),
    path('reports/course-attainment/',     CourseAttainmentView.as_view(),     name='report_course'),
    path('reports/student-summary/',       StudentSummaryView.as_view(),       name='report_student_summary'),
]


