# core/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *


class TeacherInline(admin.StackedInline):
    model = Teacher
    can_delete = False
    extra = 0


class StudentInline(admin.StackedInline):
    model = Student
    can_delete = False
    extra = 0


class CustomUserAdmin(UserAdmin):
    # Add role to the user creation/edit form
    fieldsets = UserAdmin.fieldsets + (
        ('Role', {'fields': ('role',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role', {'fields': ('role',)}),
    )
    inlines = [TeacherInline, StudentInline]
    list_display = ['username', 'email', 'role', 'is_staff']


admin.site.register(User, CustomUserAdmin)
admin.site.register(Department)
admin.site.register(Program)
admin.site.register(ProgramObjective)
admin.site.register(GraduateAttribute)
admin.site.register(POGAMapping)
admin.site.register(Semester)
admin.site.register(Course)
admin.site.register(CourseOffering)
admin.site.register(Enrollment)
admin.site.register(CLO)
admin.site.register(CLOGAMapping)
admin.site.register(Paper)
admin.site.register(Question)
admin.site.register(QuestionCLOMapping)
admin.site.register(QuestionGAMapping)
admin.site.register(StudentAnswer)
admin.site.register(CLOAttainment)
admin.site.register(GAAttainment)
admin.site.register(POAttainment)