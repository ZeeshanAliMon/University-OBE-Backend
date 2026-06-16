from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Department, Program, ProgramObjective, POGAMapping,
    GraduateAttribute, QAProfile, InstructorProfile, Student,
    Course, InstructorCourse, MarksCategory, UnitItem,
    OBEQuestion, CourseStudent, StudentMark, OBEStudentMark,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ('username', 'email', 'role', 'is_active', 'is_staff')
    list_filter   = ('role', 'is_active', 'is_staff')
    fieldsets     = BaseUserAdmin.fieldsets + (('OBE Role', {'fields': ('role',)}),)
    add_fieldsets = BaseUserAdmin.add_fieldsets + (('OBE Role', {'fields': ('role',)}),)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display  = ('slug', 'name')
    search_fields = ('slug', 'name')


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display  = ('slug', 'code', 'name', 'department')
    list_filter   = ('department',)
    search_fields = ('slug', 'code', 'name')


class POGAMappingInline(admin.TabularInline):
    model = POGAMapping
    extra = 1


@admin.register(ProgramObjective)
class ProgramObjectiveAdmin(admin.ModelAdmin):
    list_display = ('program', 'code', 'description')
    list_filter  = ('program',)
    inlines      = [POGAMappingInline]


@admin.register(GraduateAttribute)
class GraduateAttributeAdmin(admin.ModelAdmin):
    list_display  = ('ga_id', 'name', 'department', 'program')
    list_filter   = ('department', 'program')
    search_fields = ('ga_id', 'name')


@admin.register(QAProfile)
class QAProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'department', 'employee_id')
    list_filter   = ('department',)
    search_fields = ('user__username', 'employee_id')


@admin.register(InstructorProfile)
class InstructorProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'employee_id', 'department', 'designation')
    list_filter   = ('department',)
    search_fields = ('user__username', 'employee_id')


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display  = ('roll_number', 'user', 'program', 'batch_year')
    list_filter   = ('program', 'batch_year')
    search_fields = ('roll_number', 'user__username')


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display      = ('slug', 'code', 'title', 'type', 'department', 'program')
    list_filter       = ('type', 'department', 'program')
    search_fields     = ('slug', 'code', 'title')
    filter_horizontal = ('mapped_gas',)


class MarksCategoryInline(admin.TabularInline):
    model  = MarksCategory
    extra  = 0
    fields = ('name', 'percentage', 'units', 'order')


@admin.register(InstructorCourse)
class InstructorCourseAdmin(admin.ModelAdmin):
    list_display  = ('code', 'title', 'instructor', 'department', 'program', 'credit_hours', 'updated_at')
    list_filter   = ('department', 'program')
    search_fields = ('code', 'title', 'instructor__user__username', 'frontend_id')
    readonly_fields = ('frontend_id', 'created_at', 'updated_at')
    inlines       = [MarksCategoryInline]


class UnitItemInline(admin.TabularInline):
    model  = UnitItem
    extra  = 0
    fields = ('unit_no', 'total_marks', 'passing', 'weightage')


@admin.register(MarksCategory)
class MarksCategoryAdmin(admin.ModelAdmin):
    list_display = ('course', 'name', 'percentage', 'units', 'order')
    list_filter  = ('course__department',)
    inlines      = [UnitItemInline]


@admin.register(UnitItem)
class UnitItemAdmin(admin.ModelAdmin):
    list_display = ('category', 'unit_no', 'total_marks', 'passing', 'weightage')
    list_filter  = ('category__course__department',)


@admin.register(OBEQuestion)
class OBEQuestionAdmin(admin.ModelAdmin):
    list_display  = ('course', 'category_name', 'unit_no', 'question_name', 'max_marks')
    list_filter   = ('course__department',)
    search_fields = ('question_name', 'course__code')


@admin.register(CourseStudent)
class CourseStudentAdmin(admin.ModelAdmin):
    list_display  = ('reg_no', 'name', 'course')
    list_filter   = ('course__department',)
    search_fields = ('reg_no', 'name')


@admin.register(StudentMark)
class StudentMarkAdmin(admin.ModelAdmin):
    list_display = ('student', 'category_name', 'unit_no', 'score')
    list_filter  = ('category_name',)
    search_fields = ('student__reg_no',)


@admin.register(OBEStudentMark)
class OBEStudentMarkAdmin(admin.ModelAdmin):
    list_display  = ('student', 'question', 'score')
    search_fields = ('student__reg_no',)
