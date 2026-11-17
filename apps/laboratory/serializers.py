from rest_framework import serializers
from .models import Laboratory, Instrument


class InstrumentSerializer(serializers.ModelSerializer):
    laboratory_name = serializers.CharField(source='laboratory.name', read_only=True)
    area_name = serializers.CharField(source='area.name', read_only=True, allow_null=True)

    class Meta:
        model = Instrument
        fields = [
            'id', 'asset_tag', 'name', 'laboratory', 'laboratory_name',
            'area', 'area_name', 'manufacturer', 'model_number',
            'serial_number', 'max_temperature_c', 'max_load_kn',
            'is_operational', 'next_calibration_due', 'created_at'
        ]


class LaboratorySerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source='facility.name', read_only=True)
    facility_code = serializers.CharField(source='facility.code', read_only=True)
    instruments = InstrumentSerializer(many=True, read_only=True)

    class Meta:
        model = Laboratory
        fields = ['id', 'facility', 'facility_name', 'facility_code', 'name', 'accreditation_scope', 'is_operational', 'instruments', 'created_at']
