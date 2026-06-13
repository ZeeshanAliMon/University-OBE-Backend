from rest_framework import serializers
from .models import (
    User, Department, Program, ProgramObjective, POGAMapping,
    GraduateAttribute, QAProfile, InstructorProfile, Course,
    InstructorCourse,
)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class UserSerializer(serializers.ModelSerializer):
    user_type = serializers.CharField(source='role')

    class Meta:
        model  = User
        fields = ['id', 'username', 'email', 'user_type']


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
            'departmentId', 'programId',
            'credit_hours',
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


class InstructorCourseSerializer(serializers.ModelSerializer):
    """
    Full InstructorCourse object matching frontend InstructorCourse type exactly.

    Read shape:
    {
        "id":            "course-demo-1",
        "code":          "SE-311",
        "title":         "Software Engineering",
        "departmentId":  "computing",
        "departmentName":"Department of Computing and Technology",
        "programId":     "bscs",
        "programName":   "Bachelor of Science in Computer Science (BSCS)",
        "creditHours":   3,
        "categories":    [...],
        "unitsData":     {...},
        "students":      [...],
        "obeQuestions":  [...],   ← NEW
        "obeMarks":      {...}    ← NEW
    }
    """
    id             = serializers.CharField(source='frontend_id')
    departmentId   = serializers.CharField(source='department.slug',  read_only=True)
    departmentName = serializers.CharField(source='department.name',  read_only=True)
    programId      = serializers.SerializerMethodField()
    programName    = serializers.SerializerMethodField()
    creditHours    = serializers.IntegerField(source='credit_hours')
    unitsData      = serializers.JSONField(source='units_data')
    obeQuestions   = serializers.JSONField(source='obe_questions')   # NEW
    obeMarks       = serializers.JSONField(source='obe_marks')       # NEW

    class Meta:
        model  = InstructorCourse
        fields = [
            'id', 'code', 'title',
            'departmentId', 'departmentName',
            'programId',    'programName',
            'creditHours',
            'categories',
            'unitsData',
            'students',
            'obeQuestions',
            'obeMarks',
        ]

    def get_programId(self, obj):
        return obj.program.slug if obj.program else None

    def get_programName(self, obj):
        if not obj.program:
            return None
        return f"{obj.program.name} ({obj.program.code})"