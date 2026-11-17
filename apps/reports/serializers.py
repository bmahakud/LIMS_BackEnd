from rest_framework import serializers
from .models import LaboratoryReport, ConsolidatedReport, ReportRevision


class LaboratoryReportSerializer(serializers.ModelSerializer):
    sample_code = serializers.CharField(source='sample.sample_code', read_only=True)
    issued_by_name = serializers.CharField(source='issued_by.get_full_name', read_only=True)

    class Meta:
        model = LaboratoryReport
        fields = [
            'id', 'report_number', 'sample', 'sample_code',
            'status', 'revision_number', 'report_snapshot_json',
            'sha256_hash', 'issued_by', 'issued_by_name',
            'issued_at', 'created_at'
        ]


class ConsolidatedReportSerializer(serializers.ModelSerializer):
    project_code = serializers.CharField(source='project.code', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)

    class Meta:
        model = ConsolidatedReport
        fields = [
            'id', 'crc_number', 'project', 'project_code', 'title',
            'status', 'samples', 'report_snapshot_json', 'sha256_hash',
            'approved_by', 'approved_by_name', 'approved_at', 'created_at'
        ]


class IssueReportRequestSerializer(serializers.Serializer):
    sample_id = serializers.UUIDField()
    specification_set_id = serializers.UUIDField()
    outcome = serializers.CharField()
    decision_notes = serializers.CharField()
