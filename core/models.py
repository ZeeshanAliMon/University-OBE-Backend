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
    code        = models.CharField(max_length=10)   # 'PO1', 'PO2'
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ('program', 'code')
        ordering        = ['code']

    def __str__(self):
        return f"{self.program.code} | {self.code}"


class GraduateAttribute(models.Model):
    ga_id       = models.CharField(max_length=30, unique=True)   # 'GA-1', 'GA-B1'
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


# ─── Instructor Course ────────────────────────────────────────────────────────

class InstructorCourse(models.Model):
    """
    Header record for an instructor's course offering.

    Grading system choices match frontend exactly:
      'ready1'  → standard absolute grading template (A=90+, B=80+, ...)
      'ready2'  → alternative absolute template
      'custom'  → instructor-defined grade boundaries (stored in GradeScale table)
    """
    GRADING_SYSTEM_CHOICES = [
        ('ready1', 'Standard Absolute'),
        ('ready2', 'Alternative Absolute'),
        ('custom', 'Custom'),
    ]

    instructor              = models.ForeignKey(
        InstructorProfile, on_delete=models.CASCADE, related_name='instructor_courses'
    )
    frontend_id             = models.CharField(max_length=100)
    code                    = models.CharField(max_length=30)
    title                   = models.CharField(max_length=200)
    department              = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='instructor_courses'
    )
    program                 = models.ForeignKey(
        Program, on_delete=models.PROTECT,
        related_name='instructor_courses', null=True, blank=True
    )
    credit_hours            = models.IntegerField(default=3)
    clo_count               = models.IntegerField(default=4)
    selected_grading_system = models.CharField(
        max_length=10, choices=GRADING_SYSTEM_CHOICES, default='ready1'
    )
    created_at              = models.DateTimeField(auto_now_add=True)
    updated_at              = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('instructor', 'frontend_id')

    def __str__(self):
        return f"{self.code} — {self.title} ({self.instructor.user.username})"


# ─── Grading Scale ────────────────────────────────────────────────────────────

class GradeScale(models.Model):
    """
    Custom grade boundaries for a course when selectedGradingSystem = 'custom'.
    One row per grade letter.

    Frontend type:
      customGradingSystem: { grade: string, percentage: string, points: string }[]
    e.g. { grade: 'A', percentage: '90', points: '4.0' }

    Was a JSONField before. Now a proper table so you can:
    - query "how many students got an A in this course"
    - validate that grade boundaries don't overlap
    - reuse a scale across multiple courses in future
    """
    course     = models.ForeignKey(
        InstructorCourse, on_delete=models.CASCADE, related_name='grade_scale'
    )
    grade      = models.CharField(max_length=5)    # 'A', 'A-', 'B+', 'F'
    min_percentage = models.FloatField()            # lower boundary e.g. 90.0
    points     = models.FloatField()                # GPA points e.g. 4.0
    order      = models.IntegerField(default=0)    # display order

    class Meta:
        unique_together = ('course', 'grade')
        ordering        = ['order']

    def __str__(self):
        return f"{self.course.code} | {self.grade} >= {self.min_percentage}% ({self.points} pts)"


# ─── Marks Categories ────────────────────────────────────────────────────────

class MarksCategory(models.Model):
    """
    One assessment category per course.
    e.g. Assignments (15%, 3 units), Quizzes (10%, 3 units), Final (30%, 1 unit)
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

    mapped_clos is a JSONField here because CLOs are not yet FK rows —
    they are string labels ('CLO-1', 'CLO-2') that the instructor defines
    per-course. When the CLO table is added in future this becomes a M2M.

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
    # Intentional JSONField — CLO labels are not yet a separate table.
    # e.g. ["CLO-1", "CLO-2"]

    class Meta:
        unique_together = ('category', 'unit_no')
        ordering        = ['unit_no']

    def __str__(self):
        return f"{self.category} | Unit {self.unit_no}"


# ─── OBE Questions ────────────────────────────────────────────────────────────

class OBEQuestion(models.Model):
    """
    A question inside a unit, linked to CLOs.
    Frontend type: OBEQuestion { id, categoryName, unitNo, questionName, maxMarks, mappedCLOs }
    UnitQuestion  { id, name, maxMarks, mappedCLOs }

    unit_item FK is set when possible for direct DB traversal.
    category_name + unit_no are kept as denormalized fields so the
    frontend shape can be reconstructed without extra joins.

    mapped_clos is JSONField for same reason as UnitItem.mapped_clos.
    """
    course        = models.ForeignKey(
        InstructorCourse, on_delete=models.CASCADE, related_name='obe_questions'
    )
    unit_item     = models.ForeignKey(
        UnitItem, on_delete=models.SET_NULL, related_name='questions',
        null=True, blank=True
    )
    frontend_id   = models.CharField(max_length=100)
    category_name = models.CharField(max_length=100)
    unit_no       = models.IntegerField()
    question_name = models.CharField(max_length=200)
    max_marks     = models.FloatField(default=0)
    mapped_clos   = models.JSONField(default=list)
    order         = models.IntegerField(default=0)

    class Meta:
        unique_together = ('course', 'frontend_id')
        ordering        = ['order']

    def __str__(self):
        return f"{self.course.code} | {self.category_name}-{self.unit_no} | {self.question_name}"


# ─── Course Students ──────────────────────────────────────────────────────────

class CourseStudent(models.Model):
    """
    A student enrolled in an instructor's course.
    reg_no is the student's registration number as entered by the instructor
    (e.g. 'FA22-BSCS-0012'). No FK to Student model — instructors type
    reg numbers manually or import from Excel.
    Frontend type: CourseStudent { regNo, name, marks? }
    """
    course = models.ForeignKey(
        InstructorCourse, on_delete=models.CASCADE, related_name='students'
    )
    reg_no = models.CharField(max_length=60)
    name   = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ('course', 'reg_no')

    def __str__(self):
        return f"{self.reg_no} — {self.course.code}"


# ─── Student Marks ────────────────────────────────────────────────────────────

class StudentMark(models.Model):
    """
    One mark entry: student × unit_item.
    FK to UnitItem for integrity + queryability.
    category_name + unit_no kept as denormalized fields for fast
    reconstruction of the frontend marks dict without joins.

    Frontend key format: '{categoryName}-{unitNo}' e.g. 'Assignments-1'
    Frontend type: marks: Record<string, number>
    """
    student   = models.ForeignKey(
        CourseStudent, on_delete=models.CASCADE, related_name='marks'
    )
    unit_item = models.ForeignKey(
        UnitItem, on_delete=models.CASCADE, related_name='student_marks'
    )
    score     = models.FloatField(default=0)

    class Meta:
        unique_together = ('student', 'unit_item')

    def __str__(self):
        return (
            f"{self.student.reg_no} | "
            f"{self.unit_item.category.name}-{self.unit_item.unit_no} = {self.score}"
        )


# ─── OBE Student Marks ───────────────────────────────────────────────────────

class OBEStudentMark(models.Model):
    """
    One OBE mark: student × question.
    FK to both CourseStudent and OBEQuestion for full integrity.
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
