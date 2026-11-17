from rest_framework import serializers
from .models import TestDefinition, TestMethod, SpecificationSet, SpecificationLimit, TestPlanTemplate


class TestMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestMethod
        fields = ['id', 'standard_code', 'title', 'organization', 'applicable_product_category', 'is_accredited']


class TestDefinitionSerializer(serializers.ModelSerializer):
    methods = TestMethodSerializer(many=True, read_only=True)

    class Meta:
        model = TestDefinition
        fields = [
            'id', 'code', 'name', 'discipline', 'default_unit',
            'specimen_requirement_desc', 'standard_turnaround_days',
            'is_active', 'methods'
        ]


class SpecificationLimitSerializer(serializers.ModelSerializer):
    test_code = serializers.CharField(source='test_definition.code', read_only=True)
    test_name = serializers.CharField(source='test_definition.name', read_only=True)

    class Meta:
        model = SpecificationLimit
        fields = ['id', 'test_definition', 'test_code', 'test_name', 'material_grade', 'min_value', 'max_value', 'unit', 'is_critical']


class SpecificationSetSerializer(serializers.ModelSerializer):
    limits = SpecificationLimitSerializer(many=True, read_only=True)

    class Meta:
        model = SpecificationSet
        fields = ['id', 'code', 'title', 'revision', 'is_active', 'limits']


class TestPlanTemplateSerializer(serializers.ModelSerializer):
    methods = TestMethodSerializer(many=True, read_only=True)

    class Meta:
        model = TestPlanTemplate
        fields = ['id', 'name', 'description', 'methods', 'is_active']
