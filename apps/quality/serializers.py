from rest_framework import serializers
from .models import QAReview, Deviation, FinalDecision


class DeviationSerializer(serializers.ModelSerializer):
    justified_by_name = serializers.CharField(source='justified_by.get_full_name', read_only=True)

    class Meta:
        model = Deviation
        fields = ['id', 'qa_review', 'severity', 'deviation_description', 'technical_justification', 'is_acceptable', 'justified_by', 'justified_by_name', 'created_at']
        read_only_fields = ['id', 'justified_by', 'created_at']


class QAReviewSerializer(serializers.ModelSerializer):
    parameter_code = serializers.CharField(source='result.parameter_code', read_only=True)
    measured_text = serializers.CharField(source='result.raw_input_text', read_only=True)
    limit_min = serializers.CharField(source='specification_limit.min_value', read_only=True, allow_null=True)
    limit_max = serializers.CharField(source='specification_limit.max_value', read_only=True, allow_null=True)
    deviation = DeviationSerializer(read_only=True)

    class Meta:
        model = QAReview
        fields = [
            'id', 'result', 'parameter_code', 'measured_text',
            'specification_limit', 'limit_min', 'limit_max',
            'evaluation_status', 'delta_from_limit', 'evaluation_notes',
            'deviation', 'reviewed_at'
        ]


class FinalDecisionSerializer(serializers.ModelSerializer):
    approver_name = serializers.CharField(source='approver.get_full_name', read_only=True)
    sample_code = serializers.CharField(source='sample.sample_code', read_only=True)

    class Meta:
        model = FinalDecision
        fields = [
            'id', 'sample', 'sample_code', 'specification_set',
            'outcome', 'approver', 'approver_name', 'decision_notes',
            'decided_at'
        ]
        read_only_fields = ['id', 'approver', 'decided_at']
