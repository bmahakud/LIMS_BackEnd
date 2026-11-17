from rest_framework import serializers
from .models import WorkOrder, TestAssignment


class TestAssignmentSerializer(serializers.ModelSerializer):
    specimen_code = serializers.CharField(source='specimen.specimen_code', read_only=True)
    standard_code = serializers.CharField(source='test_method.standard_code', read_only=True)
    test_name = serializers.CharField(source='test_method.test_definition.name', read_only=True)
    instrument_name = serializers.CharField(source='instrument.name', read_only=True)
    technician_name = serializers.CharField(source='assigned_technician.get_full_name', read_only=True)

    class Meta:
        model = TestAssignment
        fields = [
            'id', 'work_order', 'specimen', 'specimen_code',
            'test_method', 'standard_code', 'test_name',
            'instrument', 'instrument_name', 'assigned_technician',
            'technician_name', 'test_temperature_c', 'soaking_time_hours',
            'applied_load_mpa', 'status', 'started_at', 'completed_at'
        ]


class WorkOrderSerializer(serializers.ModelSerializer):
    laboratory_name = serializers.CharField(source='laboratory.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    assignments = TestAssignmentSerializer(many=True, read_only=True)

    class Meta:
        model = WorkOrder
        fields = [
            'id', 'order_number', 'laboratory', 'laboratory_name',
            'created_by', 'created_by_name', 'status', 'priority',
            'target_completion_date', 'assignments', 'created_at', 'updated_at'
        ]


class WorkOrderCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkOrder
        fields = [
            'id', 'order_number', 'laboratory', 'priority',
            'target_completion_date'
        ]
