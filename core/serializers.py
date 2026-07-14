from rest_framework import serializers
from .models import (
    User, Department, Program, ProgramObjective, POGAMapping,
    GraduateAttribute, Course, CLO,
    InstructorCourse, GradeScale, MarksCategory, UnitItem,
    OBEQuestion, CourseStudent, StudentMark, OBEStudentMark,
)


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class UserSerializer(serializers.ModelSerializer):
    user_type = serializers.CharField(source='role')
    name      = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = ['id', 'email', 'name', 'user_type']

    def get_name(self, obj):
        full = obj.get_full_name().strip()
        return full if full else obj.email.split('@')[0]


# ─── QA Serializers ───────────────────────────────────────────────────────────

class CLOSerializer(serializers.ModelSerializer):
    """
    Serializer for Course Learning Outcomes.
    mappedGA: GA id string (e.g. "GA-1") or null.
    """
    mappedGA = serializers.SerializerMethodField()

    class Meta:
        model  = CLO
        fields = ['id', 'code', 'description', 'mappedGA', 'order']

    def get_mappedGA(self, obj):
        return obj.mapped_ga.ga_id if obj.mapped_ga else None


class GraduateAttributeSerializer(serializers.ModelSerializer):
    id           = serializers.CharField(source='ga_id')
    departmentId = serializers.SerializerMethodField()
    programId    = serializers.SerializerMethodField()

    def get_departmentId(self, obj):
        return obj.department.dept_id if obj.department else None

    def get_programId(self, obj):
        return obj.program.code.lower() if obj.program else None

    class Meta:
        model  = GraduateAttribute
        fields = ['id', 'name', 'description', 'departmentId', 'programId']


class POSerializer(serializers.ModelSerializer):
    id        = serializers.CharField(source='code')
    text      = serializers.CharField(source='description')
    mappedGAs = serializers.SerializerMethodField()

    class Meta:
        model  = ProgramObjective
        fields = ['id', 'text', 'mappedGAs']

    def get_mappedGAs(self, obj):
        return list(
            obj.ga_mappings
               .select_related('graduate_attribute')
               .values_list('graduate_attribute__ga_id', flat=True)
        )


class DepartmentSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='dept_id')

    class Meta:
        model  = Department
        fields = ['id', 'name', 'vision', 'mission']

    def update(self, instance, validated_data):
        instance.vision  = validated_data.get('vision',  instance.vision)
        instance.mission = validated_data.get('mission', instance.mission)
        instance.name    = validated_data.get('name',    instance.name)
        instance.save()
        return instance


class ProgramSerializer(serializers.ModelSerializer):
    id           = serializers.SerializerMethodField()
    departmentId = serializers.SerializerMethodField()
    pos          = POSerializer(source='objectives', many=True, read_only=True)
    pos_write    = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=False, source='pos'
    )

    def get_id(self, obj):
        return obj.code.lower()   # 'BSCS' -> 'bscs' for frontend

    def get_departmentId(self, obj):
        return obj.department.dept_id

    class Meta:
        model  = Program
        fields = ['id', 'name', 'code', 'departmentId', 'vision', 'mission', 'pos', 'pos_write']

    def update(self, instance, validated_data):
        pos_data = validated_data.pop('pos', None)
        instance.vision  = validated_data.get('vision',  instance.vision)
        instance.mission = validated_data.get('mission', instance.mission)
        instance.name    = validated_data.get('name',    instance.name)
        instance.save()
        if pos_data is not None:
            self._sync_pos(instance, pos_data)
        return instance

    def _sync_pos(self, program, pos_data):
        for po_dict in pos_data:
            po_code    = po_dict.get('id')
            po_text    = po_dict.get('text', '')
            mapped_gas = po_dict.get('mappedGAs', [])
            po_obj, _  = ProgramObjective.objects.get_or_create(
                program=program, code=po_code, defaults={'description': po_text}
            )
            po_obj.description = po_text
            po_obj.save()
            POGAMapping.objects.filter(program_objective=po_obj).delete()
            for ga_id in mapped_gas:
                try:
                    ga = GraduateAttribute.objects.get(ga_id=ga_id)
                    POGAMapping.objects.get_or_create(
                        program_objective=po_obj, graduate_attribute=ga
                    )
                except GraduateAttribute.DoesNotExist:
                    pass


class CourseSerializer(serializers.ModelSerializer):
    id              = serializers.SerializerMethodField()
    departmentId    = serializers.SerializerMethodField()
    programId       = serializers.SerializerMethodField()
    mappedGAs       = serializers.SerializerMethodField()
    mappedGAs_write = serializers.ListField(
        child=serializers.CharField(), write_only=True, required=False, source='mapped_gas_ids'
    )
    creditHours     = serializers.IntegerField(source='credit_hours', required=False)

    class Meta:
        model  = Course
        fields = ['id', 'code', 'title', 'type', 'mappedGAs', 'mappedGAs_write',
                  'departmentId', 'programId', 'creditHours']

    def get_id(self, obj):
        return obj.code

    def get_departmentId(self, obj):
        return obj.department.dept_id

    def get_programId(self, obj):
        return obj.program.code.lower() if obj.program else None

    def get_mappedGAs(self, obj):
        return list(obj.mapped_gas.values_list('ga_id', flat=True))

    def update(self, instance, validated_data):
        mapped_gas_ids = validated_data.pop('mapped_gas_ids', None)
        instance.code  = validated_data.get('code',  instance.code)
        instance.title = validated_data.get('title', instance.title)
        instance.type  = validated_data.get('type',  instance.type)
        instance.save()
        if mapped_gas_ids is not None:
            instance.mapped_gas.set(GraduateAttribute.objects.filter(ga_id__in=mapped_gas_ids))
        return instance


# ─── Instructor Serializers ───────────────────────────────────────────────────

class UnitItemSerializer(serializers.ModelSerializer):
    unitNo     = serializers.IntegerField(source='unit_no')
    totalMarks = serializers.FloatField(source='total_marks')
    mappedCLOs = serializers.JSONField(source='mapped_clos')
    questions  = serializers.SerializerMethodField()

    class Meta:
        model  = UnitItem
        fields = ['unitNo', 'passing', 'totalMarks', 'weightage', 'mappedCLOs', 'questions']

    def get_questions(self, obj):
        return [
            {
                'id':         q.frontend_id,
                'name':       q.question_name,
                'maxMarks':   q.max_marks,
                'mappedCLOs': q.mapped_clos,
            }
            for q in obj.questions.order_by('order').all()
        ]


class MarksCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = MarksCategory
        fields = ['name', 'percentage', 'units']


class OBEQuestionSerializer(serializers.ModelSerializer):
    id           = serializers.CharField(source='frontend_id')
    categoryName = serializers.CharField(source='category_name')
    unitNo       = serializers.IntegerField(source='unit_no')
    questionName = serializers.CharField(source='question_name')
    maxMarks     = serializers.FloatField(source='max_marks')
    mappedCLOs   = serializers.JSONField(source='mapped_clos')

    class Meta:
        model  = OBEQuestion
        fields = ['id', 'categoryName', 'unitNo', 'questionName', 'maxMarks', 'mappedCLOs']


class CourseStudentSerializer(serializers.ModelSerializer):
    regNo = serializers.CharField(source='reg_no')
    marks = serializers.SerializerMethodField()

    class Meta:
        model  = CourseStudent
        fields = ['regNo', 'name', 'marks']

    def get_marks(self, obj):
        return {
            f"{m.unit_item.category.name}-{m.unit_item.unit_no}": m.score
            for m in obj.marks.select_related('unit_item__category').all()
        }


class GradeScaleSerializer(serializers.ModelSerializer):
    """
    Serializes to frontend customGradingSystem shape:
    { grade: string, percentage: string, points: string }
    percentage and points are strings in the frontend type.
    """
    percentage = serializers.SerializerMethodField()
    points     = serializers.SerializerMethodField()

    class Meta:
        model  = GradeScale
        fields = ['grade', 'percentage', 'points']

    def get_percentage(self, obj):
        return str(obj.min_percentage)

    def get_points(self, obj):
        return str(obj.points)


class InstructorCourseSerializer(serializers.ModelSerializer):
    id                    = serializers.CharField(source='frontend_id')
    courseType            = serializers.CharField(source='course_type')
    departmentId          = serializers.SerializerMethodField()
    departmentName        = serializers.CharField(source='department.name',  read_only=True)
    programId             = serializers.SerializerMethodField()
    programName           = serializers.SerializerMethodField()
    creditHours           = serializers.IntegerField(source='credit_hours')
    cloCount              = serializers.IntegerField(source='clo_count')
    selectedGradingSystem = serializers.CharField(source='selected_grading_system')
    academicYear          = serializers.CharField(source='academic_year')
    customGradingSystem   = serializers.SerializerMethodField()
    categories            = serializers.SerializerMethodField()
    unitsData             = serializers.SerializerMethodField()
    students              = serializers.SerializerMethodField()
    obeQuestions          = serializers.SerializerMethodField()
    obeMarks              = serializers.SerializerMethodField()

    class Meta:
        model  = InstructorCourse
        fields = [
            'id', 'code', 'title', 'courseType',
            'departmentId', 'departmentName',
            'programId', 'programName',
            'creditHours', 'cloCount', 'academicYear',
            'selectedGradingSystem', 'customGradingSystem',
            'categories', 'unitsData',
            'students', 'obeQuestions', 'obeMarks',
        ]

    def get_departmentId(self, obj):
        return obj.department.dept_id

    def get_programId(self, obj):
        return obj.program.code.lower() if obj.program else None

    def get_programName(self, obj):
        if not obj.program:
            return None
        return f"{obj.program.name} ({obj.program.code})"

    def get_customGradingSystem(self, obj):
        return GradeScaleSerializer(obj.grade_scale.all(), many=True).data

    def get_categories(self, obj):
        # MarksCategory now belongs to the catalog Course, not InstructorCourse
        # directly (migration 0011) — shared across every instructor/term
        # teaching the same course. Reached via catalog_course.
        if not obj.catalog_course_id:
            return []
        return MarksCategorySerializer(obj.catalog_course.markscategories.all(), many=True).data

    def get_unitsData(self, obj):
        result = {}
        if not obj.catalog_course_id:
            return result
        for cat in obj.catalog_course.markscategories.all():
            result[cat.name] = UnitItemSerializer(cat.unit_items.all(), many=True).data
        return result

    def get_students(self, obj):
        return CourseStudentSerializer(
            obj.students.prefetch_related('marks__unit_item__category').all(),
            many=True
        ).data

    def get_obeQuestions(self, obj):
        import logging
        logger = logging.getLogger(__name__)
        questions = obj.obe_questions.all()
        count = questions.count()
        logger.warning(f"🔍 FETCHING OBE QUESTIONS: course={obj.code}, count={count}")
        for q in questions:
            logger.warning(f"   - q_id={q.id}, frontend_id={q.frontend_id}, name={q.question_name}, unit_item={q.unit_item}")
        return OBEQuestionSerializer(questions, many=True).data

    def get_obeMarks(self, obj):
        result = {}
        for student in obj.students.prefetch_related('obe_marks__question').all():
            student_marks = {
                om.question.frontend_id: om.score
                for om in student.obe_marks.all()
            }
            if student_marks:
                result[student.reg_no] = student_marks
        return result




# ─── Write Serializers (validation for raw-create endpoints) ─────────────────
# These are used on POST/PATCH paths where views previously called
# objects.create() / objects.save() directly, skipping model-level validation
# (max_length, choices, blank constraints).  They reject bad data at the API
# boundary with a clear 400 before anything touches the database.

class ProgramWriteSerializer(serializers.Serializer):
    name         = serializers.CharField(max_length=200)
    code         = serializers.CharField(max_length=20)
    vision       = serializers.CharField(required=False, allow_blank=True, default='')
    mission      = serializers.CharField(required=False, allow_blank=True, default='')
    departmentId = serializers.CharField()


class GraduateAttributeWriteSerializer(serializers.Serializer):
    id           = serializers.CharField(max_length=30)   # ga_id
    name         = serializers.CharField(max_length=200)
    description  = serializers.CharField(required=False, allow_blank=True, default='')
    departmentId = serializers.CharField()
    programId    = serializers.CharField(required=False, allow_blank=True, default='')


class CourseWriteSerializer(serializers.Serializer):
    COURSE_TYPE_CHOICES = ['core', 'elective']

    code         = serializers.CharField(max_length=30)
    title        = serializers.CharField(max_length=200)
    type         = serializers.ChoiceField(choices=COURSE_TYPE_CHOICES, default='core')
    departmentId = serializers.CharField()
    programId    = serializers.CharField(required=False, allow_blank=True, default='')
    creditHours  = serializers.IntegerField(required=False, default=3, min_value=0, max_value=20)
    mappedGAs    = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )


class CLOWriteSerializer(serializers.Serializer):
    code        = serializers.CharField(max_length=20)
    description = serializers.CharField(allow_blank=True, default='')
    mappedGA    = serializers.CharField(required=False, allow_null=True, default=None)
    order       = serializers.IntegerField(required=False, default=0)


class TeacherWriteSerializer(serializers.Serializer):
    name         = serializers.CharField(max_length=200)
    email        = serializers.EmailField()
    employeeId   = serializers.CharField(max_length=50)
    designation  = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    departmentId = serializers.CharField()


class StudentWriteSerializer(serializers.Serializer):
    BATCH_CHOICES    = ['Fall', 'Spring', 'Summer']
    SEMESTER_CHOICES = ['1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th']

    regNo        = serializers.CharField(max_length=60)
    name         = serializers.CharField(max_length=200)
    email        = serializers.EmailField(required=False, allow_blank=True, default='')
    departmentId = serializers.CharField()
    programId    = serializers.CharField()
    batch        = serializers.ChoiceField(choices=BATCH_CHOICES, default='Fall')
    semester     = serializers.ChoiceField(choices=SEMESTER_CHOICES, default='1st')

# ─── Admission Student ────────────────────────────────────────────────────────

class AdmissionStudentSerializer(serializers.ModelSerializer):
    """
    Frontend Student type:
    { regNo, name, email, departmentId, programId, batch, semester }
    """
    regNo        = serializers.CharField(source='reg_no')
    departmentId = serializers.SerializerMethodField()
    programId    = serializers.SerializerMethodField()

    class Meta:
        from .models import AdmissionStudent
        model  = AdmissionStudent
        fields = ['regNo', 'name', 'email', 'departmentId', 'programId', 'batch', 'semester']

    def get_departmentId(self, obj):
        return obj.department.dept_id

    def get_programId(self, obj):
        return obj.program.code.lower()
