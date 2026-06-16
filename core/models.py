from django.contrib.auth.models import AbstractUser
from django.core.validators import validate_slug
from django.db import models


# ─── Auth ─────────────────────────────────────────────────────────────────────

class User(AbstractUser):
    ROLE_CHOICES = [
        ('qa',         'QA'),
        ('instructor', 'Instructor'),
        ('student',    'Student'),
        ('admin',      'Admin'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')

    groups = models.ManyToManyField(
        'auth.Group', blank=True,
        related_name='core_users', related_query_name='core_user',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission', blank=True,
        related_name='core_users', related_query_name='core_user',
    )

    def __str__(self):
        return f"{self.username} ({self.role})"


# ─── University Structure ─────────────────────────────────────────────────────

class Department(models.Model):
    slug       = models.CharField(max_length=50, unique=True, validators=[validate_slug])
    name       = models.CharField(max_length=200, unique=True)
    vision     = models.TextField(blank=True)
    mission    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.slug} - {self.name}"


class Program(models.Model):
    slug       = models.CharField(max_length=50, unique=True, validators=[validate_slug])
    name       = models.CharField(max_length=200)
    code       = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name='programs'
    )
    vision     = models.TextField(blank=True)
    mission    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class ProgramObjective(models.Model):
    program     = models.ForeignKey(
        Program, on_delete=models.CASCADE, related_name='objectives'
    )
    code        = models.CharField(max_length=10)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ('program', 'code')
        ordering        = ['code']

    def __str__(self):
        return f"{self.program.code} | {self.code}"


class GraduateAttribute(models.Model):
    ga_id       = models.CharField(max_length=30, unique=True)
    name        = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    department  = models.ForeignKey(
        Department, on_delete=models.CASCADE,
        related_name='graduate_attributes', null=True, blank=True
    )
    program     = models.ForeignKey(
        Program, on_delete=models.CASCADE,
        related_name='graduate_attributes', null=True, blank=True
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['ga_id']

    def __str__(self):
        return f"{self.ga_id} - {self.name}"


class POGAMapping(models.Model):
    program_objective  = models.ForeignKey(
        ProgramObjective, on_delete=models.CASCADE, related_name='ga_mappings'
    )
    graduate_attribute = models.ForeignKey(
        GraduateAttribute, on_delete=models.CASCADE, related_name='po_mappings'
    )

    class Meta:
        unique_together = ('program_objective', 'graduate_attribute')


# ─── People ───────────────────────────────────────────────────────────────────

class QAProfile(models.Model):
    user        = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='qa_profile'
    )
    department  = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='qa_staff'
    )
    employee_id = models.CharField(max_length=50, unique=True, blank=True)

    def __str__(self):
        return f"QA: {self.user.username} @ {self.department.slug}"


class InstructorProfile(models.Model):
    user        = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='instructor_profile'
    )
    employee_id = models.CharField(max_length=50, unique=True)
    department  = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='instructors'
    )
    designation = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.employee_id} - {self.user.username}"


class Student(models.Model):
    user        = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='student_profile'
    )
    roll_number = models.CharField(max_length=50, unique=True)
    program     = models.ForeignKey(
        Program, on_delete=models.PROTECT, related_name='students'
    )
    batch_year  = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.roll_number} - {self.user.username}"


# ─── QA Course Catalogue ─────────────────────────────────────────────────────

class Course(models.Model):
    COURSE_TYPE_CHOICES = [('core', 'Core'), ('elective', 'Elective')]

    slug         = models.CharField(max_length=50, unique=True, validators=[validate_slug])
    code         = models.CharField(max_length=30)
    title        = models.CharField(max_length=200)
    type         = models.CharField(max_length=10, choices=COURSE_TYPE_CHOICES, default='core')
    department   = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='courses'
    )
    program      = models.ForeignKey(
        Program, on_delete=models.PROTECT,
        related_name='courses', null=True, blank=True
    )
    mapped_gas   = models.ManyToManyField(GraduateAttribute, blank=True, related_name='courses')
    credit_hours = models.IntegerField(default=3)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('code', 'program')

    def __str__(self):
        return f"{self.code} - {self.title}"


# ─── Instructor Course (header only) ─────────────────────────────────────────

class InstructorCourse(models.Model):
    """
    Core course info only. All nested data lives in child tables.
    frontend_id preserves the client-generated uuid.
    """
    GRADING_SYSTEM_CHOICES = [
        ('absolute', 'Absolute'),
        ('relative', 'Relative'),
        ('custom',   'Custom'),
    ]

    instructor            = models.ForeignKey(
        InstructorProfile, on_delete=models.CASCADE, related_name='instructor_courses'
    )
    frontend_id           = models.CharField(max_length=100)
    code                  = models.CharField(max_length=30)
    title                 = models.CharField(max_length=200)
    department            = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='instructor_courses'
    )
    program               = models.ForeignKey(
        Program, on_delete=models.PROTECT,
        related_name='instructor_courses', null=True, blank=True
    )
    credit_hours          = models.IntegerField(default=3)
    clo_count             = models.IntegerField(default=4)
    selected_grading_system = models.CharField(
        max_length=20, choices=GRADING_SYSTEM_CHOICES, default='absolute'
    )
    custom_grading_system = models.JSONField(default=list)
    # [{ "grade": "A", "percentage": "90", "points": "4.0" }, ...]
    created_at            = models.DateTimeField(auto_now_add=True)
    updated_at            = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('instructor', 'frontend_id')

    def __str__(self):
        return f"{self.code} — {self.title} ({self.instructor.user.username})"


# ─── Marks Categories ────────────────────────────────────────────────────────

class MarksCategory(models.Model):
    """
    Represents one assessment category per course.
    e.g. Assignments (15%, 3 units), Quizzes (10%, 3 units)
    Frontend type: MarksCategory { name, percentage, units }
    """
    course     = models.ForeignKey(
        InstructorCourse, on_delete=models.CASCADE, related_name='categories'
    )
    name       = models.CharField(max_length=100)
    percentage = models.FloatField(default=0)
    units      = models.IntegerField(default=0)
    order      = models.IntegerField(default=0)

    class Meta:
        unique_together = ('course', 'name')
        ordering        = ['order']

    def __str__(self):
        return f"{self.course.code} | {self.name} ({self.percentage}%)"


# ─── Unit Items ───────────────────────────────────────────────────────────────

class UnitItem(models.Model):
    """
    One unit inside a category.
    e.g. Assignment-1 (totalMarks=10, passing=5, weightage=33.3)
    Frontend type: UnitItem { unitNo, passing, totalMarks, weightage, mappedCLOs?, questions? }
    """
    category    = models.ForeignKey(
        MarksCategory, on_delete=models.CASCADE, related_name='unit_items'
    )
    unit_no     = models.IntegerField()
    passing     = models.FloatField(default=5)
    total_marks = models.FloatField(default=10)
    weightage   = models.FloatField(default=0)
    mapped_clos = models.JSONField(default=list)
    # ["CLO-1", "CLO-2"] — stored as JSON since CLOs are string labels not FK rows yet

    class Meta:
        unique_together = ('category', 'unit_no')
        ordering        = ['unit_no']

    def __str__(self):
        return f"{self.category} | Unit {self.unit_no}"


# ─── OBE Questions ────────────────────────────────────────────────────────────

class OBEQuestion(models.Model):
    """
    A question inside a unit, mapped to CLOs.
    Frontend type: OBEQuestion { id, categoryName, unitNo, questionName, maxMarks, mappedCLOs }
    """
    course        = models.ForeignKey(
        InstructorCourse, on_delete=models.CASCADE, related_name='obe_questions'
    )
    unit_item     = models.ForeignKey(
        UnitItem, on_delete=models.CASCADE, related_name='questions',
        null=True, blank=True
    )
    frontend_id   = models.CharField(max_length=100)
    category_name = models.CharField(max_length=100)
    unit_no       = models.IntegerField()
    question_name = models.CharField(max_length=200)
    max_marks     = models.FloatField(default=0)
    mapped_clos   = models.JSONField(default=list)
    # ["CLO-1", "CLO-2"]

    class Meta:
        unique_together = ('course', 'frontend_id')

    def __str__(self):
        return f"{self.course.code} | {self.category_name}-{self.unit_no} | {self.question_name}"


# ─── Course Students ──────────────────────────────────────────────────────────

class CourseStudent(models.Model):
    """
    A student enrolled in an instructor's course.
    Frontend type: CourseStudent { regNo, name, marks? }
    """
    course  = models.ForeignKey(
        InstructorCourse, on_delete=models.CASCADE, related_name='students'
    )
    reg_no  = models.CharField(max_length=60)
    name    = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ('course', 'reg_no')

    def __str__(self):
        return f"{self.reg_no} — {self.course.code}"


# ─── Student Marks ────────────────────────────────────────────────────────────

class StudentMark(models.Model):
    """
    One mark entry: student × category × unit.
    Key in frontend: '{categoryName}-{unitNo}' e.g. 'Assignments-1'
    Frontend type: marks: Record<string, number>
    """
    student       = models.ForeignKey(
        CourseStudent, on_delete=models.CASCADE, related_name='marks'
    )
    category_name = models.CharField(max_length=100)
    unit_no       = models.IntegerField()
    score         = models.FloatField(default=0)

    class Meta:
        unique_together = ('student', 'category_name', 'unit_no')

    def __str__(self):
        return f"{self.student.reg_no} | {self.category_name}-{self.unit_no} = {self.score}"


# ─── OBE Student Marks ───────────────────────────────────────────────────────

class OBEStudentMark(models.Model):
    """
    One OBE mark entry: student × question.
    Frontend type: obeMarks: Record<regNo, Record<questionId, number>>
    """
    student  = models.ForeignKey(
        CourseStudent, on_delete=models.CASCADE, related_name='obe_marks'
    )
    question = models.ForeignKey(
        OBEQuestion, on_delete=models.CASCADE, related_name='student_marks'
    )
    score    = models.FloatField(default=0)

    class Meta:
        unique_together = ('student', 'question')

    def __str__(self):
        return f"{self.student.reg_no} | {self.question.question_name} = {self.score}"
