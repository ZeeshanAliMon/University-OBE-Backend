from django.contrib.auth.models import AbstractUser
from django.core.validators import validate_slug
from django.db import models


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
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='programs')
    vision     = models.TextField(blank=True)
    mission    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class ProgramObjective(models.Model):
    program     = models.ForeignKey(Program, on_delete=models.CASCADE, related_name='objectives')
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


class QAProfile(models.Model):
    user        = models.OneToOneField(User, on_delete=models.CASCADE, related_name='qa_profile')
    department  = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='qa_staff')
    employee_id = models.CharField(max_length=50, unique=True, blank=True)

    def __str__(self):
        return f"QA: {self.user.username} @ {self.department.slug}"


class InstructorProfile(models.Model):
    user        = models.OneToOneField(User, on_delete=models.CASCADE, related_name='instructor_profile')
    employee_id = models.CharField(max_length=50, unique=True)
    department  = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='instructors')
    designation = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.employee_id} - {self.user.username}"


class Student(models.Model):
    user        = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    roll_number = models.CharField(max_length=50, unique=True)
    program     = models.ForeignKey(Program, on_delete=models.PROTECT, related_name='students')
    batch_year  = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.roll_number} - {self.user.username}"


class Course(models.Model):
    COURSE_TYPE_CHOICES = [('core', 'Core'), ('elective', 'Elective')]

    slug         = models.CharField(max_length=50, unique=True, validators=[validate_slug])
    code         = models.CharField(max_length=30)
    title        = models.CharField(max_length=200)
    type         = models.CharField(max_length=10, choices=COURSE_TYPE_CHOICES, default='core')
    department   = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='courses')
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


class InstructorCourse(models.Model):
    """
    A course specification owned by an instructor.

    JSON field breakdown matching frontend types exactly:

    categories: MarksCategory[]
        [{ "name": "Assignments", "percentage": 15, "units": 3 }, ...]

    units_data: Record<string, UnitItem[]>
        { "Assignments": [{ "unitNo":1, "passing":5, "totalMarks":10, "weightage":33.3 }], ... }

    students: CourseStudent[]
        [{ "regNo": "FA22-BSCS-0012", "name": "...", "marks": { "Assignments-1": 8.5, ... } }, ...]

    obe_questions: OBEQuestion[]   ← NEW in this update
        [{
            "id": "q-uuid-1",
            "categoryName": "Assignments",
            "unitNo": 1,
            "questionName": "Q1",
            "maxMarks": 5,
            "mappedCLOs": ["CLO-1", "CLO-2"]
        }, ...]

    obe_marks: Record<string, Record<string, number>>   ← NEW in this update
        {
            "FA22-BSCS-0012": { "q-uuid-1": 4.5, "q-uuid-2": 3.0 },
            "FA22-BSCS-0045": { "q-uuid-1": 5.0, "q-uuid-2": 2.5 }
        }
    """
    instructor   = models.ForeignKey(
        InstructorProfile, on_delete=models.CASCADE, related_name='instructor_courses'
    )
    frontend_id  = models.CharField(max_length=100)
    code         = models.CharField(max_length=30)
    title        = models.CharField(max_length=200)
    department   = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='instructor_courses'
    )
    program      = models.ForeignKey(
        Program, on_delete=models.PROTECT,
        related_name='instructor_courses', null=True, blank=True
    )
    credit_hours  = models.IntegerField(default=3)
    categories    = models.JSONField(default=list)
    units_data    = models.JSONField(default=dict)
    students      = models.JSONField(default=list)
    obe_questions = models.JSONField(default=list)   # NEW — OBEQuestion[]
    obe_marks     = models.JSONField(default=dict)   # NEW — regNo -> { questionId: marks }
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('instructor', 'frontend_id')

    def __str__(self):
        return f"{self.code} — {self.title} ({self.instructor.user.username})"
