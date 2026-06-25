from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AdmissionStudentListView, AdmissionStudentDetailView,
    LoginView,
    DepartmentListView, DepartmentDetailView,
    ProgramListView, ProgramDetailView,
    GraduateAttributeListView,
    CourseListView, CourseDetailView,
    InstructorCourseView,
)

urlpatterns = [
    path('auth/login/',         LoginView.as_view(),         name='login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(),  name='token_refresh'),

    path('departments/',            DepartmentListView.as_view(),   name='department_list'),
    path('departments/<str:slug>/', DepartmentDetailView.as_view(), name='department_detail'),

    path('programs/',            ProgramListView.as_view(),   name='program_list'),
    path('programs/<str:slug>/', ProgramDetailView.as_view(), name='program_detail'),

    path('gas/', GraduateAttributeListView.as_view(), name='ga_list'),

    path('courses/',            CourseListView.as_view(),   name='course_list'),
    path('courses/<str:slug>/', CourseDetailView.as_view(), name='course_detail'),

    path('instructor/courses/', InstructorCourseView.as_view(), name='instructor_courses'),

    path('students/',             AdmissionStudentListView.as_view(),   name='student_list'),
    path('students/<str:reg_no>/',AdmissionStudentDetailView.as_view(), name='student_detail'),
]
