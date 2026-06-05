from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('auth/login/',                        views.login),
    path('auth/refresh/',                      TokenRefreshView.as_view()),
    path('data/',                              views.all_data),
    path('departments/',                       views.departments_list),
    path('departments/<str:dept_id>/',         views.department_detail),
    path('programs/',                          views.programs_list),
    path('programs/<str:program_id>/',         views.program_detail),   # now handles PATCH
    path('gas/',                               views.gas_list),
]