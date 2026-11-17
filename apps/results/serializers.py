from rest_framework import serializers
from .models import TestRun, Measurement, Result, ResultRevision, ResultVerification, RetestRequest


class MeasurementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Measurement
        fields = ['id', 'parameter_name', 'raw_input_text', 'numeric_value', 'qualifier', 'unit', 'measured_at']


class ResultSerializer(serializers.ModelSerializer):
    technician_name = serializers.CharField(source='technician.get_full_name', read_only=True)
    method_code = serializers.CharField(source='test_method.standard_code', read_only=True)
    specimen_code = serializers.CharField(source='test_run.assignment.specimen.specimen_code', read_only=True)

    class Meta:
        model = Result
        fields = [
            'id', 'test_run', 'specimen_code', 'test_method', 'method_code',
            'parameter_code', 'raw_input_text', 'numeric_value', 'qualifier',
            'unit', 'is_manual_entry', 'technician', 'technician_name',
            'revision_number', 'verification_status', 'is_latest', 'recorded_at'
        ]
        read_only_fields = ['id', 'revision_number', 'verification_status', 'is_latest', 'recorded_at']


class ResultVerificationSerializer(serializers.ModelSerializer):
    verified_by_name = serializers.CharField(source='verified_by.get_full_name', read_only=True)

    class Meta:
        model = ResultVerification
        fields = ['id', 'result', 'verified_by', 'verified_by_name', 'verified_at', 'comments']
        read_only_fields = ['id', 'verified_by', 'verified_at']


class TestRunSerializer(serializers.ModelSerializer):
    technician_name = serializers.CharField(source='technician.get_full_name', read_only=True)
    instrument_name = serializers.CharField(source='instrument.name', read_only=True)
    measurements = MeasurementSerializer(many=True, read_only=True)
    results = ResultSerializer(many=True, read_only=True)

    class Meta:
        model = TestRun
        fields = [
            'id', 'assignment', 'run_number', 'technician', 'technician_name',
            'instrument', 'instrument_name', 'started_at', 'completed_at',
            'status', 'ambient_temp_c', 'ambient_relative_humidity_pct',
            'remarks', 'measurements', 'results'
        ]


class RetestRequestSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.CharField(source='requested_by.get_full_name', read_only=True)

    class Meta:
        model = RetestRequest
        fields = ['id', 'original_result', 'reason', 'requested_by', 'requested_by_name', 'status', 'requested_at']
        read_only_fields = ['id', 'requested_by', 'requested_at']
