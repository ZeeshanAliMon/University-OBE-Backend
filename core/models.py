from django.contrib.auth.models import AbstractUser
from django.db import models


# ─── Auth ─────────────────────────────────────────────────────────────────────

class User(AbstractUser):
    email               = models.EmailField(unique=True)   # login identifier
    must_change_password = models.BooleanField(default=False)  # True on first login
    ROLE_CHOICES = [
        ('qa',         'QA'),
        ('instructor', 'Instructor'),
        ('student',    'Student'),
        ('admission',  'Admission'),
        ('dept_admin', 'Department Admin'),
        ('admin',      'Admin'),
    ]
    role = models.CharField(
        max_length=20, choices=ROLE_CHOICES,
        blank=True, default='',   # blank — admin must consciously pick a role
    )

    groups = models.ManyToManyField(
        'auth.Group', blank=True,
        related_name='core_users', related_query_name='core_user',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission', blank=True,
        related_name='core_users', related_query_name='core_user',
    )

    class Meta:
        verbose_name        = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        full = self.get_full_name()
        return f"{full} ({self.username})" if full else self.username


# ─── University Structure ─────────────────────────────────────────────────────

class Department(models.Model):
    dept_id    = models.CharField(max_length=50, unique=True)   # e.g. 'computing', 'business'
    name       = models.CharField(max_length=200, unique=True)
    vision     = models.TextField(blank=True)
    mission    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Department'
        verbose_name_plural = 'Departments'
        ordering            = ['name']

    def __str__(self):
        return self.name


class Program(models.Model):
    name       = models.CharField(max_length=200)
    code       = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT,   # FIXED: was CASCADE
        related_name='programs'
    )
    vision     = models.TextField(blank=True)
    mission    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Program'
        verbose_name_plural = 'Programs'
        ordering            = ['code']

    def __str__(self):
        return f"{self.code} — {self.name}"


class ProgramObjective(models.Model):
    program     = models.ForeignKey(
        Program, on_delete=models.CASCADE, related_name='objectives'
    )
    code        = models.CharField(max_length=10)   # 'PO1', 'PO2'
    description = models.TextField(blank=True)

    class Meta:
        verbose_name        = 'Program Objective'
        verbose_name_plural = 'Program Objectives'
        unique_together     = ('program', 'code')
        ordering            = ['code']

    def __str__(self):
        return f"{self.program.code} | {self.code}"


class GraduateAttribute(models.Model):
    ga_id       = models.CharField(max_length=30, unique=True)
    name        = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    department  = models.ForeignKey(
        Department, on_delete=models.PROTECT,   # FIXED: NOT NULL — GA must have a dept
        related_name='graduate_attributes'
    )
    program     = models.ForeignKey(
        Program, on_delete=models.SET_NULL,     # optional program scope
        related_name='graduate_attributes',
        null=True, blank=True
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Graduate Attribute'
        verbose_name_plural = 'Graduate Attributes'
        ordering            = ['ga_id']

    def __str__(self):
        return f"{self.ga_id} — {self.name}"


class POGAMapping(models.Model):
    program_objective  = models.ForeignKey(
        ProgramObjective, on_delete=models.CASCADE, related_name='ga_mappings'
    )
    graduate_attribute = models.ForeignKey(
        GraduateAttribute, on_delete=models.CASCADE, related_name='po_mappings'
    )

    class Meta:
        verbose_name        = 'PO → GA Mapping'
        verbose_name_plural = 'PO → GA Mappings'
        unique_together     = ('program_objective', 'graduate_attribute')

    def __str__(self):
        return f"{self.program_objective} → {self.graduate_attribute.ga_id}"


# ─── People ───────────────────────────────────────────────────────────────────

class QAProfile(models.Model):
    user        = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='qa_profile'
    )
    department  = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='qa_staff'
    )
    employee_id = models.CharField(max_length=50, unique=True, blank=True)

    class Meta:
        verbose_name        = 'QA Profile'
        verbose_name_plural = 'QA Profiles'

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} — QA @ {self.department.name}"


class InstructorProfile(models.Model):
    user        = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='instructor_profile'
    )
    employee_id = models.CharField(max_length=50, unique=True, blank=True)   # FIXED: blank=True for consistency
    department  = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='instructors'
    )
    designation = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name        = 'Instructor Profile'
        verbose_name_plural = 'Instructor Profiles'

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} — {self.designation or 'Instructor'}"


class Student(models.Model):
    """
    Links an auth User to a student reg_no.
    Same pattern as InstructorProfile and QAProfile.

    Created either:
    a) When admission officer creates a student and assigns them a login, or
    b) Manually in admin.

    reg_no must match AdmissionStudent.reg_no for full data access.
    """
    BATCH_YEAR_CHOICES = [(y, str(y)) for y in range(2018, 2035)]

    user        = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='student_profile'
    )
    reg_no      = models.CharField(max_length=60, unique=True)
    program     = models.ForeignKey(
        Program, on_delete=models.PROTECT, related_name='students'
    )
    department  = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='students',
        null=True, blank=True
    )
    batch_year  = models.IntegerField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Student Profile'
        verbose_name_plural = 'Student Profiles'
        ordering            = ['reg_no']

    def __str__(self):
        return f"{self.reg_no} — {self.user.get_full_name() or self.user.username}"


# ─── QA Course Catalogue ─────────────────────────────────────────────────────

class Course(models.Model):
    COURSE_TYPE_CHOICES = [('core', 'Core'), ('elective', 'Elective')]
    COURSE_SUBTYPE_CHOICES = [('theory', 'Theory'), ('lab', 'Lab')]

    # unique=True removed — same course code can exist across multiple programs
    # within a department (e.g. CMC371 taught in both BSCS and BSSE).
    # Uniqueness is now enforced at the (code, department) level via
    # unique_together below — you can't add the same code twice in the same
    # department, but the same code can appear in different programs of that
    # same department as separate catalog entries.
    code         = models.CharField(max_length=30)
    title        = models.CharField(max_length=200)
    type         = models.CharField(max_length=10, choices=COURSE_TYPE_CHOICES, default='core')
    subtype         = models.CharField(max_length=10, choices=COURSE_SUBTYPE_CHOICES, default='theory')
    department   = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='courses'
    )
    program      = models.ForeignKey(
        Program, on_delete=models.PROTECT,
        related_name='courses', null=True, blank=True
    )
    mapped_gas   = models.ManyToManyField(
        GraduateAttribute, blank=True, related_name='courses'
    )
    credit_hours = models.IntegerField(default=3)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Course'
        verbose_name_plural = 'Courses'
        ordering            = ['code']
        unique_together     = [('code', 'department', 'program')]

    def __str__(self):
        return f"{self.code} — {self.title}"


# ─── Course Learning Outcomes (CLOs) ────────────────────────────────────────
#
# Replaces the string-based ["CLO-1", "CLO-2"] JSON approach.
# UnitItem.mapped_clos and OBEQuestion.mapped_clos JSON fields are kept
# as migration path — they store CLO codes like "CLO-1" which match
# CLO.code below.
#

class CLO(models.Model):
    """
    A Course Learning Outcome — belongs to one InstructorCourse.
    mapped_ga: which Graduate Attribute this CLO contributes to.
    code: human-readable label like "CLO-1", "CLO-2" — matches JSON fields.
    """
    course      = models.ForeignKey(
        'InstructorCourse', on_delete=models.CASCADE, related_name='clos'
    )
    code        = models.CharField(max_length=20)          # e.g. "CLO-1"
    description = models.TextField(blank=True, default='') # e.g. "Explain syntax..."
    mapped_ga   = models.ForeignKey(
        GraduateAttribute, on_delete=models.SET_NULL,
        related_name='mapped_clos', null=True, blank=True
    )
    order       = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name        = 'CLO'
        verbose_name_plural = 'CLOs'
        unique_together     = ('course', 'code')
        ordering            = ['order', 'code']

    def __str__(self):
        return f"{self.course.code} — {self.code}: {self.description[:60]}"


# ─── Instructor Course ────────────────────────────────────────────────────────

class InstructorCourse(models.Model):
    """
    Header record for an instructor's course offering.
    Grading system choices match frontend exactly:
      'ready1' → Standard absolute  (A=90+, B=80+, ...)
      'ready2' → Alternative absolute
      'custom' → Instructor-defined boundaries (stored in GradeScale)
    """
    GRADING_SYSTEM_CHOICES = [
        ('ready1', 'Standard Absolute'),
        ('ready2', 'Alternative Absolute'),
        ('custom', 'Custom'),
    ]

    instructor              = models.ForeignKey(
        InstructorProfile, on_delete=models.CASCADE, related_name='instructor_courses'
    )
    frontend_id             = models.CharField(max_length=100, db_index=True)
    course_type             = models.CharField(
        max_length=10,
        choices=[('Theory', 'Theory'), ('Lab', 'Lab')],
        default='Theory'
    )
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
    # Semester and academic year — required for cohort comparison reports
    semester                = models.CharField(
        max_length=10, blank=True,
        choices=[
            ('1st','1st'),('2nd','2nd'),('3rd','3rd'),('4th','4th'),
            ('5th','5th'),('6th','6th'),('7th','7th'),('8th','8th'),
        ]
    )
    academic_year           = models.CharField(
        max_length=20, blank=True
    )   # e.g. 'Fall-2024', 'Spring-2025'

    # ── Semester lifecycle ────────────────────────────────────────────────────
    STATUS_CHOICES = [
        ('active', 'Active — editable'),
        ('closed', 'Closed — finalized, read-only'),
    ]
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    closed_at   = models.DateTimeField(null=True, blank=True)
    closed_by   = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='closed_courses'
    )

    created_at              = models.DateTimeField(auto_now_add=True)
    updated_at              = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Instructor Course'
        verbose_name_plural = 'Instructor Courses'
        # frontend_id now bakes in academic_year — same teacher+course in a
        # different term is a DIFFERENT row, never overwrites prior terms
        unique_together     = ('instructor', 'frontend_id')
        ordering            = ['-updated_at']

    @property
    def is_locked(self):
        return self.status == 'closed'

    def __str__(self):
        term = f" [{self.academic_year}]" if self.academic_year else ''
        return f"{self.code} — {self.title}{term} [{self.instructor.user.get_full_name() or self.instructor.user.username}] ({self.status})"


# ─── Grade Scale ─────────────────────────────────────────────────────────────

class GradeScale(models.Model):
    """
    Custom grade boundaries per course (used when selectedGradingSystem = 'custom').
    Frontend shape: { grade: string, percentage: string, points: string }
    """
    course         = models.ForeignKey(
        InstructorCourse, on_delete=models.CASCADE, related_name='grade_scale'
    )
    grade          = models.CharField(max_length=5)
    min_percentage = models.FloatField()
    points         = models.FloatField()
    order          = models.IntegerField(default=0)

    class Meta:
        verbose_name        = 'Grade Scale Entry'
        verbose_name_plural = 'Grade Scale'
        unique_together     = ('course', 'grade')
        ordering            = ['order']

    def __str__(self):
        return f"{self.course.code} | {self.grade} ≥ {self.min_percentage}% ({self.points} pts)"


# ─── Marks Categories ────────────────────────────────────────────────────────

class MarksCategory(models.Model):
    """
    Assessment category per course.
    e.g. Assignments (15%, 3 units), Mid Term (20%, 1 unit)
    Frontend type: MarksCategory { name, percentage, units }
    """
    course      = models.ForeignKey(
        InstructorCourse, on_delete=models.CASCADE, related_name='categories'
    )
    name        = models.CharField(max_length=100)
    percentage  = models.FloatField(default=0)
    units       = models.IntegerField(default=0)
    order       = models.IntegerField(default=0)

    class Meta:
        verbose_name        = 'Marks Category'
        verbose_name_plural = 'Marks Categories'
        unique_together     = ('course', 'name')
        ordering            = ['order']

    def __str__(self):
        return f"{self.course.code} | {self.name} ({self.percentage}%)"


# ─── Unit Items ───────────────────────────────────────────────────────────────

class UnitItem(models.Model):
    """
    One unit inside a category.
    e.g. Assignment-1, Quiz-2, Mid Term-1
    Frontend type: UnitItem { unitNo, passing, totalMarks, weightage, mappedCLOs?, questions? }

    mapped_clos is JSONField — CLO labels are string-based until the CLO
    table is introduced in the next phase, at which point this becomes M2M.
    """
    category    = models.ForeignKey(
        MarksCategory, on_delete=models.CASCADE, related_name='unit_items'
    )
    unit_no     = models.IntegerField()
    passing     = models.FloatField(default=5)
    total_marks = models.FloatField(default=10)
    weightage   = models.FloatField(default=0)
    mapped_clos = models.JSONField(default=list)

    class Meta:
        verbose_name        = 'Unit Item'
        verbose_name_plural = 'Unit Items'
        unique_together     = ('category', 'unit_no')
        ordering            = ['unit_no']

    def __str__(self):
        return f"{self.category.course.code} | {self.category.name} — Unit {self.unit_no}"


# ─── OBE Questions ────────────────────────────────────────────────────────────

class OBEQuestion(models.Model):
    """
    A question inside a unit, mapped to CLOs.
    Frontend types: OBEQuestion + UnitQuestion
    mapped_clos is JSONField for same reason as UnitItem.mapped_clos.
    """
    course        = models.ForeignKey(
        InstructorCourse, on_delete=models.CASCADE, related_name='obe_questions'
    )
    unit_item     = models.ForeignKey(
        UnitItem, on_delete=models.SET_NULL,
        related_name='questions', null=True, blank=True
    )
    frontend_id   = models.CharField(max_length=100)
    category_name = models.CharField(max_length=100)
    unit_no       = models.IntegerField()
    question_name = models.CharField(max_length=200)
    max_marks     = models.FloatField(default=0)
    mapped_clos   = models.JSONField(default=list)
    order         = models.IntegerField(default=0)

    class Meta:
        verbose_name        = 'OBE Question'
        verbose_name_plural = 'OBE Questions'
        unique_together     = ('course', 'frontend_id')
        ordering            = ['order']

    def __str__(self):
        return f"{self.course.code} | {self.category_name}-{self.unit_no} | {self.question_name}"


# ─── Course Students ──────────────────────────────────────────────────────────

class CourseStudent(models.Model):
    """
    A student enrolled in an instructor's course.
    reg_no is entered manually by the instructor or imported from Excel.
    No FK to Student — keeps the instructor workflow independent.
    Frontend type: CourseStudent { regNo, name, marks? }
    """
    course = models.ForeignKey(
        InstructorCourse, on_delete=models.CASCADE, related_name='students'
    )
    reg_no = models.CharField(max_length=60, db_index=True)
    name   = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name        = 'Course Student'
        verbose_name_plural = 'Course Students'
        unique_together     = ('course', 'reg_no')
        ordering            = ['reg_no']

    def __str__(self):
        return f"{self.reg_no} — {self.name or 'Unnamed'} ({self.course.code})"


# ─── Student Marks ────────────────────────────────────────────────────────────

class StudentMark(models.Model):
    """
    One mark: student × unit_item.
    FK to UnitItem ensures marks are deleted if the unit is removed.
    Frontend key: '{categoryName}-{unitNo}' e.g. 'Assignments-1'
    """
    student   = models.ForeignKey(
        CourseStudent, on_delete=models.CASCADE, related_name='marks'
    )
    unit_item = models.ForeignKey(
        UnitItem, on_delete=models.CASCADE, related_name='student_marks'
    )
    score     = models.FloatField(default=0)

    class Meta:
        verbose_name        = 'Student Mark'
        verbose_name_plural = 'Student Marks'
        unique_together     = ('student', 'unit_item')

    def __str__(self):
        return (
            f"{self.student.reg_no} | "
            f"{self.unit_item.category.name}-{self.unit_item.unit_no} = {self.score}"
        )


# ─── OBE Student Marks ───────────────────────────────────────────────────────

class OBEStudentMark(models.Model):
    """
    One OBE mark: student × question.
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
        verbose_name        = 'OBE Student Mark'
        verbose_name_plural = 'OBE Student Marks'
        unique_together     = ('student', 'question')

    def __str__(self):
        return f"{self.student.reg_no} | {self.question.question_name} = {self.score}"


# ─── Admission Student Registry ───────────────────────────────────────────────

class AdmissionStudent(models.Model):
    """
    Students registered through the Admission dashboard.
    Separate from the auth Student model — this is the university
    student registry managed by the admission officer.

    Frontend type:
    { regNo, name, departmentId, programId, batch: 'Spring'|'Summer'|'Fall' }
    """
    BATCH_CHOICES = [
        ('Spring', 'Spring'),
        ('Summer', 'Summer'),
        ('Fall',   'Fall'),
    ]
    SEMESTER_CHOICES = [
        ('1st', '1st'), ('2nd', '2nd'), ('3rd', '3rd'), ('4th', '4th'),
        ('5th', '5th'), ('6th', '6th'), ('7th', '7th'), ('8th', '8th'),
    ]

    reg_no     = models.CharField(max_length=60, unique=True)
    name       = models.CharField(max_length=200)
    email      = models.EmailField(blank=True, default='')
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT,
        related_name='admission_students'
    )
    program    = models.ForeignKey(
        Program, on_delete=models.PROTECT,
        related_name='admission_students'
    )
    batch      = models.CharField(max_length=10, choices=BATCH_CHOICES, default='Fall')
    semester   = models.CharField(max_length=10, choices=SEMESTER_CHOICES, default='1st')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Admission Student'
        verbose_name_plural = 'Admission Students'
        ordering            = ['reg_no']

    def __str__(self):
        return f"{self.reg_no} — {self.name} ({self.program.code}, {self.batch})"


# ─── Dept Admin Profile ───────────────────────────────────────────────────────

class DeptAdminProfile(models.Model):
    user        = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='dept_admin_profile'
    )
    employee_id = models.CharField(max_length=50, unique=True, blank=True)
    department  = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='dept_admins'
    )

    class Meta:
        verbose_name        = 'Dept Admin Profile'
        verbose_name_plural = 'Dept Admin Profiles'

    def __str__(self):
        return f"{self.user.username} — Admin @ {self.department.name}"


# ─── Admission Officer Profile ────────────────────────────────────────────────

class AdmissionProfile(models.Model):
    user        = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='admission_profile'
    )
    employee_id = models.CharField(max_length=50, unique=True, blank=True)
    department  = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='admission_officers'
    )

    class Meta:
        verbose_name        = 'Admission Profile'
        verbose_name_plural = 'Admission Profiles'

    def __str__(self):
        return f"{self.user.username} — Admission @ {self.department.name}"


# ─── Course Assignment (Dept Admin assigns instructor to course+program) ───────

class CourseAssignment(models.Model):
    """
    Junction table: one instructor teaches one course for one program.
    Compound key (instructor, course, program) is unique — no collisions.
    This decouples the course catalog from active teaching instances.
    """
    instructor = models.ForeignKey(
        InstructorProfile, on_delete=models.CASCADE, related_name='course_assignments'
    )
    course     = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name='assignments'
    )
    program    = models.ForeignKey(
        Program, on_delete=models.SET_NULL,
        related_name='course_assignments', null=True, blank=True
    )
    assigned_by   = models.ForeignKey(
        DeptAdminProfile, on_delete=models.SET_NULL,
        related_name='assignments_made', null=True, blank=True
    )
    # Term this assignment is for — e.g. 'Fall-2024'. Blank = current/ongoing
    # default assignment (legacy behavior, kept for backward compatibility).
    academic_year = models.CharField(max_length=20, blank=True, default='')
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Course Assignment'
        verbose_name_plural = 'Course Assignments'
        # Same teacher CAN teach the same course+program again in a new term —
        # academic_year makes each term's assignment a distinct row.
        unique_together     = ('instructor', 'course', 'program', 'academic_year')
        ordering            = ['course__code']

    def __str__(self):
        prog = self.program.code if self.program else 'All'
        return f"{self.instructor.user.username} → {self.course.code} ({prog})"


# ─── Semester Plan ────────────────────────────────────────────────────────────

class SemesterPlan(models.Model):
    SEMESTER_CHOICES = [
        ('1st','1st'),('2nd','2nd'),('3rd','3rd'),('4th','4th'),
        ('5th','5th'),('6th','6th'),('7th','7th'),('8th','8th'),
    ]

    program      = models.ForeignKey(
        Program, on_delete=models.CASCADE, related_name='semester_plans'
    )
    semester     = models.CharField(max_length=10, choices=SEMESTER_CHOICES)
    course_codes = models.JSONField(default=list)
    updated_by   = models.ForeignKey(
        DeptAdminProfile, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='semester_plans'
    )
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Semester Plan'
        verbose_name_plural = 'Semester Plans'
        unique_together     = ('program', 'semester')
        ordering            = ['program__code', 'semester']

    def __str__(self):
        return f"{self.program.code} — Semester {self.semester} ({len(self.course_codes)} courses)"


# ─── Final Result (Permanent Transcript Record) ─────────────────────────────
#
# Snapshot taken when a course is "closed" at semester end.
# This is the permanent academic record — independent of the live gradebook.
# If a teacher later changes subjects, gets reassigned, or the InstructorCourse
# is archived, FinalResult rows are untouched. Transcripts always read from here
# for closed terms.

class FinalResult(models.Model):
    student_reg_no   = models.CharField(max_length=60, db_index=True)
    student_name     = models.CharField(max_length=200)
    course_code      = models.CharField(max_length=30, db_index=True)
    course_title      = models.CharField(max_length=200)
    instructor_name  = models.CharField(max_length=200)   # snapshot — not FK, survives instructor reassignment
    department       = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='final_results'
    )
    program          = models.ForeignKey(
        Program, on_delete=models.PROTECT, null=True, blank=True, related_name='final_results'
    )
    academic_year    = models.CharField(max_length=20, blank=True)   # e.g. 'Fall-2024'
    semester         = models.CharField(max_length=10, blank=True)
    credit_hours     = models.IntegerField(default=3)
    final_percentage = models.FloatField(default=0.0)
    grade_letter     = models.CharField(max_length=5, blank=True)
    grade_points     = models.FloatField(default=0.0)
    clo_attainments  = models.JSONField(default=dict)   # snapshot: { "CLO-1": 78.5, ... }
    source_course    = models.ForeignKey(
        InstructorCourse, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='final_results'
    )
    finalized_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Final Result'
        verbose_name_plural = 'Final Results'
        unique_together     = ('student_reg_no', 'course_code', 'academic_year')
        ordering            = ['-finalized_at']

    def __str__(self):
        return f"{self.student_reg_no} — {self.course_code} ({self.academic_year}): {self.grade_letter}"
