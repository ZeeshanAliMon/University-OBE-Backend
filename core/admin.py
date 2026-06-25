from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django import forms
from .models import (
    User, Department, Program, ProgramObjective, POGAMapping,
    GraduateAttribute, QAProfile, InstructorProfile, Student,
    Course, InstructorCourse, GradeScale, MarksCategory, UnitItem,
    OBEQuestion, CourseStudent, StudentMark, OBEStudentMark,
    AdmissionStudent,
)


# ─── Inline profiles ──────────────────────────────────────────────────────────

class QAProfileInline(admin.StackedInline):
    model       = QAProfile
    can_delete  = False
    verbose_name = 'QA Profile'
    fields      = ('department', 'employee_id')
    extra       = 0


class InstructorProfileInline(admin.StackedInline):
    model       = InstructorProfile
    can_delete  = False
    verbose_name = 'Instructor Profile'
    fields      = ('department', 'employee_id', 'designation')
    extra       = 0


class StudentProfileInline(admin.StackedInline):
    model       = Student
    can_delete  = False
    verbose_name = 'Student Profile'
    fields      = ('program', 'roll_number', 'batch_year')
    extra       = 0


# ─── User Admin — all profiles in one page ────────────────────────────────────

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ('username', 'email', 'first_name', 'last_name', 'role', 'is_active')
    list_filter   = ('role', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name')

    fieldsets = (
        (None,           {'fields': ('username', 'password')}),
        ('Personal Info',{'fields': ('first_name', 'last_name', 'email')}),
        ('OBE Role',     {'fields': ('role',)}),
        ('Permissions',  {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields':  ('username', 'first_name', 'last_name', 'email',
                        'role', 'password1', 'password2'),
        }),
    )

    def get_inlines(self, request, obj=None):
        """Show the relevant profile inline based on the user's role."""
        if obj is None:
            return []
        if obj.role == 'qa':
            return [QAProfileInline]
        if obj.role == 'instructor':
            return [InstructorProfileInline]
        if obj.role == 'student':
            return [StudentProfileInline]
        return []


# ─── Department ───────────────────────────────────────────────────────────────

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display  = ('slug', 'name')
    search_fields = ('slug', 'name')


# ─── Program ──────────────────────────────────────────────────────────────────

@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display  = ('slug', 'code', 'name', 'department')
    list_filter   = ('department',)
    search_fields = ('slug', 'code', 'name')


# ─── Program Objectives ───────────────────────────────────────────────────────

class POGAMappingInline(admin.TabularInline):
    model = POGAMapping
    extra = 1


@admin.register(ProgramObjective)
class ProgramObjectiveAdmin(admin.ModelAdmin):
    list_display = ('program', 'code', 'description')
    list_filter  = ('program',)
    inlines      = [POGAMappingInline]


# ─── Graduate Attributes ──────────────────────────────────────────────────────

@admin.register(GraduateAttribute)
class GraduateAttributeAdmin(admin.ModelAdmin):
    list_display  = ('ga_id', 'name', 'department', 'program')
    list_filter   = ('department', 'program')
    search_fields = ('ga_id', 'name')


# ─── Profiles (standalone — still accessible separately if needed) ────────────

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


# ─── QA Courses ───────────────────────────────────────────────────────────────

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display      = ('slug', 'code', 'title', 'type', 'department', 'program')
    list_filter       = ('type', 'department', 'program')
    search_fields     = ('slug', 'code', 'title')
    filter_horizontal = ('mapped_gas',)


# ─── Instructor Course ────────────────────────────────────────────────────────

class GradeScaleInline(admin.TabularInline):
    model    = GradeScale
    extra    = 0
    fields   = ('grade', 'min_percentage', 'points', 'order')
    ordering = ('order',)


class MarksCategoryInline(admin.TabularInline):
    model    = MarksCategory
    extra    = 0
    fields   = ('name', 'percentage', 'units', 'order')
    ordering = ('order',)


@admin.register(InstructorCourse)
class InstructorCourseAdmin(admin.ModelAdmin):
    list_display    = ('code', 'title', 'instructor', 'department',
                       'program', 'credit_hours', 'selected_grading_system', 'updated_at')
    list_filter     = ('department', 'program', 'selected_grading_system')
    search_fields   = ('code', 'title', 'instructor__user__username', 'frontend_id')
    readonly_fields = ('frontend_id', 'created_at', 'updated_at')
    inlines         = [GradeScaleInline, MarksCategoryInline]


# ─── Marks Category ───────────────────────────────────────────────────────────

class UnitItemInline(admin.TabularInline):
    model    = UnitItem
    extra    = 0
    fields   = ('unit_no', 'total_marks', 'passing', 'weightage', 'mapped_clos')
    ordering = ('unit_no',)


@admin.register(MarksCategory)
class MarksCategoryAdmin(admin.ModelAdmin):
    list_display  = ('course', 'name', 'percentage', 'units', 'order')
    list_filter   = ('course__department',)
    search_fields = ('name', 'course__code')
    inlines       = [UnitItemInline]


# ─── Grade Scale ──────────────────────────────────────────────────────────────

@admin.register(GradeScale)
class GradeScaleAdmin(admin.ModelAdmin):
    list_display  = ('course', 'grade', 'min_percentage', 'points', 'order')
    list_filter   = ('course__department',)
    search_fields = ('grade', 'course__code')


# ─── Unit Item ────────────────────────────────────────────────────────────────

@admin.register(UnitItem)
class UnitItemAdmin(admin.ModelAdmin):
    list_display  = ('category', 'unit_no', 'total_marks', 'passing', 'weightage')
    list_filter   = ('category__course__department',)
    search_fields = ('category__name', 'category__course__code')


# ─── OBE Question ─────────────────────────────────────────────────────────────

@admin.register(OBEQuestion)
class OBEQuestionAdmin(admin.ModelAdmin):
    list_display  = ('course', 'category_name', 'unit_no', 'question_name', 'max_marks', 'order')
    list_filter   = ('course__department', 'category_name')
    search_fields = ('question_name', 'course__code', 'frontend_id')


# ─── Course Student ───────────────────────────────────────────────────────────

@admin.register(CourseStudent)
class CourseStudentAdmin(admin.ModelAdmin):
    list_display  = ('reg_no', 'name', 'course')
    list_filter   = ('course__department',)
    search_fields = ('reg_no', 'name', 'course__code')


# ─── Student Mark ─────────────────────────────────────────────────────────────

@admin.register(StudentMark)
class StudentMarkAdmin(admin.ModelAdmin):
    list_display  = ('student', 'unit_item', 'score')
    list_filter   = ('unit_item__category__name',)
    search_fields = ('student__reg_no', 'student__name')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'student', 'unit_item__category__course'
        )


# ─── OBE Student Mark ─────────────────────────────────────────────────────────

@admin.register(OBEStudentMark)
class OBEStudentMarkAdmin(admin.ModelAdmin):
    list_display  = ('student', 'question', 'score')
    list_filter   = ('question__course__department',)
    search_fields = ('student__reg_no', 'student__name', 'question__question_name')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'student__course', 'question__course'
        )


# ─── Admission Students ───────────────────────────────────────────────────────

@admin.register(AdmissionStudent)
class AdmissionStudentAdmin(admin.ModelAdmin):
    list_display  = ('reg_no', 'name', 'department', 'program', 'batch', 'created_at')
    list_filter   = ('department', 'program', 'batch')
    search_fields = ('reg_no', 'name')
    ordering      = ('reg_no',)
