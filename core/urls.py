from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    LoginView,
    DepartmentListView, DepartmentDetailView,
    ProgramListView, ProgramDetailView,
    GraduateAttributeListView,
    CourseListView, CourseDetailView,
    InstructorCourseView,
)

urlpatterns = [

    # ── Auth ──────────────────────────────────────────────────────────────────
    path('auth/login/',         LoginView.as_view(),         name='login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(),  name='token_refresh'),

    # ── QA: Departments ───────────────────────────────────────────────────────
    # GET   /api/departments/
    # GET   /api/departments/<slug>/
    # PATCH /api/departments/<slug>/   body: { vision, mission }
    path('departments/',            DepartmentListView.as_view(),   name='department_list'),
    path('departments/<str:slug>/', DepartmentDetailView.as_view(), name='department_detail'),

    # ── QA: Programs ──────────────────────────────────────────────────────────
    # GET   /api/programs/
    # GET   /api/programs/<slug>/
    # PATCH /api/programs/<slug>/   body: { vision, mission, pos:[…] }
    path('programs/',            ProgramListView.as_view(),   name='program_list'),
    path('programs/<str:slug>/', ProgramDetailView.as_view(), name='program_detail'),

    # ── QA: Graduate Attributes ───────────────────────────────────────────────
    # GET  /api/gas/
    path('gas/', GraduateAttributeListView.as_view(), name='ga_list'),

    # ── QA: Courses ───────────────────────────────────────────────────────────
    # GET   /api/courses/
    # GET   /api/courses/<slug>/
    # PATCH /api/courses/<slug>/   body: { mappedGAs:[…] }   ← called on every checkbox toggle
    path('courses/',            CourseListView.as_view(),   name='course_list'),
    path('courses/<str:slug>/', CourseDetailView.as_view(), name='course_detail'),

    # ── Instructor Courses ────────────────────────────────────────────────────
    # GET  /api/instructor/courses/
    #        → returns the authenticated instructor's courses list
    # POST /api/instructor/courses/
    #        body: { "courses": [ { id, code, title, departmentId, programId,
    #                               creditHours, categories, unitsData, students }, … ] }
    #        → bulk-upserts the entire list and returns it back
    path('instructor/courses/', InstructorCourseView.as_view(), name='instructor_courses'),
]
