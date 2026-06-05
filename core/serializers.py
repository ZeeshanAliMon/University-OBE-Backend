from rest_framework import serializers
from .models import (
    Department, Program, ProgramObjective,
    GraduateAttribute, POGAMapping, User
)


class GraduateAttributeSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()

    class Meta:
        model  = GraduateAttribute
        fields = ['id', 'name', 'description']

    def get_id(self, obj):
        return obj.code.lower()   # GA1 → "ga1"


class ProgramObjectiveSerializer(serializers.ModelSerializer):
    id        = serializers.SerializerMethodField()
    text      = serializers.CharField(source='description')
    mappedGAs = serializers.SerializerMethodField()

    class Meta:
        model  = ProgramObjective
        fields = ['id', 'text', 'mappedGAs']

    def get_id(self, obj):
        return obj.code.lower()   # PO1 → "po1"

    def get_mappedGAs(self, obj):
        return [
            m.graduate_attribute.code.lower()
            for m in obj.ga_mappings.select_related('graduate_attribute').all()
        ]


class ProgramSerializer(serializers.ModelSerializer):
    id           = serializers.SerializerMethodField()
    departmentId = serializers.SerializerMethodField()
    pos          = ProgramObjectiveSerializer(
                       source='objectives', many=True, read_only=True
                   )

    class Meta:
        model  = Program
        fields = ['id', 'name', 'code', 'departmentId', 'pos']

    def get_id(self, obj):
        return obj.code.lower()   # BSCS → "bscs"

    def get_departmentId(self, obj):
        return obj.department.code.lower()   # CS → "cs"

    def update(self, instance, validated_data):
        pos_data = self.context['request'].data.get('pos', None)
        instance = super().update(instance, validated_data)

        if pos_data is None:
            return instance

        keep_po_ids = []

        for po_item in pos_data:
            # Frontend may send either 'code'/'description' OR 'id'/'text'
            po_code = (po_item.get('code') or po_item.get('id') or '').upper()
            text    = po_item.get('description') or po_item.get('text') or ''
            mapped_gas = po_item.get('mappedGAs', [])

            po_obj, _ = ProgramObjective.objects.update_or_create(
                program=instance,
                code=po_code,
                defaults={'description': text}
            )
            keep_po_ids.append(po_obj.id)

            # Sync GA mappings
            po_obj.ga_mappings.all().delete()
            for ga_code_str in mapped_gas:
                ga_code = ga_code_str.upper()    # "ga1" → "GA1"
                try:
                    ga = GraduateAttribute.objects.get(code=ga_code)
                    POGAMapping.objects.create(
                        program_objective=po_obj,
                        graduate_attribute=ga
                    )
                except GraduateAttribute.DoesNotExist:
                    pass

        # Delete POs not in the incoming list
        instance.objectives.exclude(id__in=keep_po_ids).delete()

        return instance

class DepartmentSerializer(serializers.ModelSerializer):
    id       = serializers.SerializerMethodField()
    programs = ProgramSerializer(many=True, read_only=True)

    class Meta:
        model  = Department
        fields = ['id', 'name', 'vision', 'mission', 'programs']

    def get_id(self, obj):
        return obj.code.lower()   # CS → "cs"


class UserSerializer(serializers.ModelSerializer):
    user_type = serializers.CharField(source='role')

    class Meta:
        model  = User
        fields = ['id', 'username', 'email', 'user_type']