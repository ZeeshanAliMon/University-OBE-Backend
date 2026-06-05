from django.contrib.auth.models import AbstractUser
from django.db import models


# ─── Auth ────────────────────────────────────────────────────────────────────

class User(AbstractUser):
    ROLE_CHOICES = [
        ('qa',   'QA'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
    ]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')

    groups = models.ManyToManyField(
        'auth.Group',
        blank=True,
        related_name='core_users',
        related_query_name='core_user',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        blank=True,
        related_name='core_users',
        related_query_name='core_user',
    )

    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"


# ─── University Structure ─────────────────────────────────────────────────────

class Department(models.Model):
    name       = models.CharField(max_length=200, unique=True)
    code       = models.CharField(max_length=20, unique=True)
    vision     = models.TextField(blank=True)
    mission    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class Program(models.Model):
    name       = models.CharField(max_length=200)
    code       = models.CharField(max_length=20, unique=True)
    
    
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='programs')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class ProgramObjective(models.Model):
    """PO1–PO4, defined independently per program."""
    program     = models.ForeignKey(Program, on_delete=models.CASCADE, related_name='objectives')
    code        = models.CharField(max_length=10)       # PO1, PO2, PO3, PO4
    description = models.TextField()
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('program', 'code')
        ordering = ['code']

    def __str__(self):
        return f"{self.program.code} | {self.code}"


class GraduateAttribute(models.Model):
    code        = models.CharField(max_length=10, unique=True)  # GA1 … GA10
    name        = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class POGAMapping(models.Model):
    """One PO can map to many GAs. Both must belong to the same program."""
    program_objective  = models.ForeignKey(
        ProgramObjective, on_delete=models.CASCADE, related_name='ga_mappings'
    )
    graduate_attribute = models.ForeignKey(
        GraduateAttribute, on_delete=models.CASCADE, related_name='po_mappings'
    )

    class Meta:
        unique_together = ('program_objective', 'graduate_attribute')


    def __str__(self):
        return f"{self.program_objective} → {self.graduate_attribute.code}"


# ─── Semester ─────────────────────────────────────────────────────────────────

class Semester(models.Model):
    name       = models.CharField(max_length=100, unique=True)
    start_date = models.DateField(null=True, blank=True)
    end_date   = models.DateField(null=True, blank=True)
    is_active  = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# ─── People ───────────────────────────────────────────────────────────────────

class Teacher(models.Model):
    user        = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    employee_id = models.CharField(max_length=50, unique=True)
    department  = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='teachers')
    designation = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.employee_id} - {self.user.get_full_name()}"


class Student(models.Model):
    user        = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    roll_number = models.CharField(max_length=50, unique=True)
    program     = models.ForeignKey(Program, on_delete=models.PROTECT, related_name='students')
    batch_year  = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.roll_number} - {self.user.get_full_name()}"


# ─── Courses ──────────────────────────────────────────────────────────────────

class Course(models.Model):
    code         = models.CharField(max_length=20, unique=True)
    name         = models.CharField(max_length=200)
    credit_hours = models.IntegerField(default=3)
    department   = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='courses')
    created_at   = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class CourseOffering(models.Model):
    course     = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='offerings')
    program    = models.ForeignKey(Program, on_delete=models.PROTECT, related_name='offerings')
    semester   = models.ForeignKey(Semester, on_delete=models.PROTECT, related_name='offerings')
    teacher    = models.ForeignKey(Teacher, on_delete=models.PROTECT, related_name='offerings')
    section    = models.CharField(max_length=10, default='A')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('course', 'program', 'semester', 'section')

    def __str__(self):
        return f"{self.course.code} | {self.program.code} | {self.semester.name} | Sec {self.section}"


class Enrollment(models.Model):
    offering    = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name='enrollments')
    student     = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('offering', 'student')

    def __str__(self):
        return f"{self.student.roll_number} → {self.offering}"


# ─── Outcomes ─────────────────────────────────────────────────────────────────

class CLO(models.Model):
    BLOOMS_CHOICES = [
        ('remember',   'Remember'),
        ('understand', 'Understand'),
        ('apply',      'Apply'),
        ('analyze',    'Analyze'),
        ('evaluate',   'Evaluate'),
        ('create',     'Create'),
    ]
    course       = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='clos')
    code         = models.CharField(max_length=20)
    description  = models.TextField()
    blooms_level = models.CharField(max_length=20, choices=BLOOMS_CHOICES)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('course', 'code')

    def __str__(self):
        return f"{self.course.code} | {self.code}"


class CLOGAMapping(models.Model):
    clo                = models.ForeignKey(CLO, on_delete=models.CASCADE, related_name='ga_mappings')
    graduate_attribute = models.ForeignKey(GraduateAttribute, on_delete=models.CASCADE, related_name='clo_mappings')
    weight             = models.DecimalField(max_digits=4, decimal_places=2, default=1.0)

    class Meta:
        unique_together = ('clo', 'graduate_attribute')

    def __str__(self):
        return f"{self.clo} → {self.graduate_attribute.code} (w={self.weight})"


# ─── Assessment ───────────────────────────────────────────────────────────────

class Paper(models.Model):
    TYPE_CHOICES = [
        ('quiz',         'Quiz'),
        ('assignment',   'Assignment'),
        ('presentation', 'Presentation'),
        ('midterm',      'Midterm'),
        ('final',        'Final'),
    ]
    offering    = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name='papers')
    title       = models.CharField(max_length=200)
    type        = models.CharField(max_length=20, choices=TYPE_CHOICES)
    total_marks = models.DecimalField(max_digits=6, decimal_places=2)
    weightage   = models.DecimalField(max_digits=5, decimal_places=2)

    def __str__(self):
        return f"{self.offering.course.code} | {self.title}"


class Question(models.Model):
    paper           = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name='questions')
    text            = models.TextField()
    max_marks       = models.DecimalField(max_digits=6, decimal_places=2)
    cognitive_level = models.CharField(max_length=20, choices=CLO.BLOOMS_CHOICES, blank=True)

    def __str__(self):
        return f"Q{self.id} | {self.paper}"


class QuestionCLOMapping(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='clo_mappings')
    clo      = models.ForeignKey(CLO, on_delete=models.CASCADE, related_name='question_mappings')
    weight   = models.DecimalField(max_digits=4, decimal_places=2, default=1.0)

    class Meta:
        unique_together = ('question', 'clo')


class QuestionGAMapping(models.Model):
    question           = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='ga_mappings')
    graduate_attribute = models.ForeignKey(GraduateAttribute, on_delete=models.CASCADE, related_name='question_mappings')
    weight             = models.DecimalField(max_digits=4, decimal_places=2, default=1.0)

    class Meta:
        unique_together = ('question', 'graduate_attribute')


class StudentAnswer(models.Model):
    question       = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    student        = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='answers')
    marks_obtained = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    graded_by      = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='graded_answers'
    )
    graded_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('question', 'student')

    def __str__(self):
        return f"{self.student.roll_number} | Q{self.question.id} | {self.marks_obtained}/{self.question.max_marks}"


# ─── Attainment Cache ─────────────────────────────────────────────────────────

class CLOAttainment(models.Model):
    offering              = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name='clo_attainments')
    student               = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='clo_attainments')
    clo                   = models.ForeignKey(CLO, on_delete=models.CASCADE, related_name='attainments')
    attainment_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    computed_at           = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('offering', 'student', 'clo')

    def __str__(self):
        return f"{self.student.roll_number} | {self.clo.code} | {self.attainment_percentage}%"


class GAAttainment(models.Model):
    offering              = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name='ga_attainments')
    student               = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='ga_attainments')
    graduate_attribute    = models.ForeignKey(GraduateAttribute, on_delete=models.CASCADE, related_name='attainments')
    attainment_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    computed_at           = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('offering', 'student', 'graduate_attribute')

    def __str__(self):
        return f"{self.student.roll_number} | {self.graduate_attribute.code} | {self.attainment_percentage}%"


class POAttainment(models.Model):
    offering              = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name='po_attainments')
    student               = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='po_attainments')
    program_objective     = models.ForeignKey(ProgramObjective, on_delete=models.CASCADE, related_name='attainments')
    attainment_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    computed_at           = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('offering', 'student', 'program_objective')

    def __str__(self):
        return f"{self.student.roll_number} | {self.program_objective.code} | {self.attainment_percentage}%"