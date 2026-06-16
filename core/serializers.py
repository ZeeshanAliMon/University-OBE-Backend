from rest_framework import serializers
from .models import (
    User, Department, Program, ProgramObjective, POGAMapping,
    GraduateAttribute, Course,
    InstructorCourse, MarksCategory, UnitItem,
    OBEQuestion, CourseStudent, StudentMark, OBEStudentMark,
)


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class UserSerializer(serializers.ModelSerializer):
    user_type = serializers.CharField(source='role')

    class Meta:
        model  = User
        fields = ['id', 'username', 'email', 'user_type']


# ─── QA Serializers ───────────────────────────────────────────────────────────

class GraduateAttributeSerializer(serializers.ModelSerializer):
    id           = serializers.CharField(source='ga_id')
    departmentId = serializers.CharField(source='department.slug', read_only=True, default=None)
    programId    = serializers.CharField(source='program.slug',    read_only=True, default=None)

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
    id = serializers.CharField(source='slug', read_only=True)

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
    id           = serializers.CharField(source='slug', read_only=True)
    departmentId = serializers.CharField(source='department.slug', read_only=True)
    pos          = POSerializer(source='objectives', many=True, read_only=True)
    pos_write    = serializers.ListField(
        child=serializers.DictField(), write_only=True,
        required=False, source='pos'
    )

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
                program=program, code=po_code,
                defaults={'description': po_text}
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
    id           = serializers.CharField(source='slug', read_only=True)
    departmentId = serializers.CharField(source='department.slug', read_only=True)
    programId    = serializers.SerializerMethodField()
    mappedGAs    = serializers.SerializerMethodField()
    mappedGAs_write = serializers.ListField(
        child=serializers.CharField(),
        write_only=True, required=False, source='mapped_gas_ids'
    )

    class Meta:
        model  = Course
        fields = [
            'id', 'code', 'title', 'type',
            'mappedGAs', 'mappedGAs_write',
            'departmentId', 'programId', 'credit_hours',
        ]

    def get_programId(self, obj):
        return obj.program.slug if obj.program else None

    def get_mappedGAs(self, obj):
        return list(obj.mapped_gas.values_list('ga_id', flat=True))

    def update(self, instance, validated_data):
        mapped_gas_ids = validated_data.pop('mapped_gas_ids', None)
        instance.code  = validated_data.get('code',  instance.code)
        instance.title = validated_data.get('title', instance.title)
        instance.type  = validated_data.get('type',  instance.type)
        instance.save()
        if mapped_gas_ids is not None:
            gas = GraduateAttribute.objects.filter(ga_id__in=mapped_gas_ids)
            instance.mapped_gas.set(gas)
        return instance


# ─── Instructor Serializers ───────────────────────────────────────────────────
# These serialize TO and FROM the exact frontend types in types.ts.
# The frontend sees the same JSON shapes as before — only the DB storage changed.

class UnitItemSerializer(serializers.ModelSerializer):
    unitNo      = serializers.IntegerField(source='unit_no')
    totalMarks  = serializers.FloatField(source='total_marks')
    mappedCLOs  = serializers.JSONField(source='mapped_clos')
    questions   = serializers.SerializerMethodField()

    class Meta:
        model  = UnitItem
        fields = ['unitNo', 'passing', 'totalMarks', 'weightage', 'mappedCLOs', 'questions']

    def get_questions(self, obj):
        # UnitQuestion shape: { id, name, maxMarks, mappedCLOs }
        return [
            {
                'id':         q.frontend_id,
                'name':       q.question_name,
                'maxMarks':   q.max_marks,
                'mappedCLOs': q.mapped_clos,
            }
            for q in obj.questions.all()
        ]


class MarksCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = MarksCategory
        fields = ['name', 'percentage', 'units']


class OBEQuestionSerializer(serializers.ModelSerializer):
    """
    Frontend OBEQuestion type:
    { id, categoryName, unitNo, questionName, maxMarks, mappedCLOs }
    """
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
    """
    Frontend CourseStudent type:
    { regNo, name, marks: Record<string, number> }
    marks key format: '{categoryName}-{unitNo}'  e.g. 'Assignments-1'
    """
    regNo = serializers.CharField(source='reg_no')
    marks = serializers.SerializerMethodField()

    class Meta:
        model  = CourseStudent
        fields = ['regNo', 'name', 'marks']

    def get_marks(self, obj):
        return {
            f"{m.category_name}-{m.unit_no}": m.score
            for m in obj.marks.all()
        }


class InstructorCourseSerializer(serializers.ModelSerializer):
    """
    Serializes InstructorCourse to the exact InstructorCourse type the frontend expects.
    All nested data is pulled from child tables and assembled here.
    The frontend sees NO difference from before — same JSON shape.
    """
    id                    = serializers.CharField(source='frontend_id')
    departmentId          = serializers.CharField(source='department.slug',  read_only=True)
    departmentName        = serializers.CharField(source='department.name',  read_only=True)
    programId             = serializers.SerializerMethodField()
    programName           = serializers.SerializerMethodField()
    creditHours           = serializers.IntegerField(source='credit_hours')
    cloCount              = serializers.IntegerField(source='clo_count')
    selectedGradingSystem = serializers.CharField(source='selected_grading_system')
    customGradingSystem   = serializers.JSONField(source='custom_grading_system')

    # Nested — assembled from child tables
    categories  = serializers.SerializerMethodField()
    unitsData   = serializers.SerializerMethodField()
    students    = serializers.SerializerMethodField()
    obeQuestions = serializers.SerializerMethodField()
    obeMarks    = serializers.SerializerMethodField()

    class Meta:
        model  = InstructorCourse
        fields = [
            'id', 'code', 'title',
            'departmentId', 'departmentName',
            'programId', 'programName',
            'creditHours', 'cloCount',
            'selectedGradingSystem', 'customGradingSystem',
            'categories', 'unitsData',
            'students', 'obeQuestions', 'obeMarks',
        ]

    def get_programId(self, obj):
        return obj.program.slug if obj.program else None

    def get_programName(self, obj):
        if not obj.program:
            return None
        return f"{obj.program.name} ({obj.program.code})"

    def get_categories(self, obj):
        # [ { name, percentage, units } ]
        return MarksCategorySerializer(
            obj.categories.all(), many=True
        ).data

    def get_unitsData(self, obj):
        # { "Assignments": [ { unitNo, passing, totalMarks, weightage, mappedCLOs, questions } ] }
        result = {}
        for cat in obj.categories.prefetch_related('unit_items__questions').all():
            result[cat.name] = UnitItemSerializer(cat.unit_items.all(), many=True).data
        return result

    def get_students(self, obj):
        # [ { regNo, name, marks: { "Assignments-1": 8.5, ... } } ]
        return CourseStudentSerializer(
            obj.students.prefetch_related('marks').all(), many=True
        ).data

    def get_obeQuestions(self, obj):
        # [ { id, categoryName, unitNo, questionName, maxMarks, mappedCLOs } ]
        return OBEQuestionSerializer(
            obj.obe_questions.all(), many=True
        ).data

    def get_obeMarks(self, obj):
        # { "FA22-BSCS-0012": { "q-uuid-1": 4.5, ... } }
        result = {}
        for student in obj.students.prefetch_related('obe_marks__question').all():
            student_marks = {}
            for obe_mark in student.obe_marks.all():
                student_marks[obe_mark.question.frontend_id] = obe_mark.score
            if student_marks:
                result[student.reg_no] = student_marks
        return result
