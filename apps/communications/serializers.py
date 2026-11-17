from rest_framework import serializers
from .models import Inquiry


class InquiryCreateSerializer(serializers.ModelSerializer):
    testRequirements = serializers.ListField(
        child=serializers.CharField(max_length=150),
        required=False,
        source='test_requirements'
    )
    sampleType = serializers.CharField(max_length=150, required=False, allow_blank=True, source='sample_type')

    class Meta:
        model = Inquiry
        fields = [
            'id', 'name', 'organization', 'email', 'phone',
            'sampleType', 'timeline', 'message', 'testRequirements',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def validate_name(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Name must be at least 2 characters long.")
        return value.strip()

    def validate_message(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Please provide at least 10 characters detailing your request.")
        return value.strip()
