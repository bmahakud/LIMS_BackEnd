from rest_framework import serializers
from .models import Sample, SampleCollection, SampleReceipt, SamplePhoto, Specimen, PreparationRecord, SampleTransfer


class SamplePhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SamplePhoto
        fields = ['id', 'image_url', 'caption', 'is_damage_evidence', 'uploaded_at']


class SampleCollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SampleCollection
        fields = ['id', 'location_description', 'sampling_protocol', 'courier_tracking_no', 'dispatch_date', 'created_at']


class SampleReceiptSerializer(serializers.ModelSerializer):
    received_by_name = serializers.CharField(source='received_by.get_full_name', read_only=True)

    class Meta:
        model = SampleReceipt
        fields = [
            'id', 'received_by', 'received_by_name', 'received_date',
            'packaging_condition', 'moisture_barrier_intact', 'heat_numbers_verified',
            'is_accepted', 'discrepancy_remarks'
        ]


class SpecimenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Specimen
        fields = [
            'id', 'specimen_code', 'sub_index', 'geometry',
            'length_mm', 'width_mm', 'height_mm', 'planarity_checked',
            'status', 'created_at'
        ]


class SampleSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source='material_lot.material.name', read_only=True)
    lot_number = serializers.CharField(source='material_lot.lot_number', read_only=True)
    project_code = serializers.CharField(source='material_lot.project.code', read_only=True)
    facility_name = serializers.CharField(source='current_facility.name', read_only=True)
    receipt_record = SampleReceiptSerializer(read_only=True)
    collection_record = SampleCollectionSerializer(read_only=True)
    photos = SamplePhotoSerializer(many=True, read_only=True)
    specimens = SpecimenSerializer(many=True, read_only=True)

    class Meta:
        model = Sample
        fields = [
            'id', 'sample_code', 'material_lot', 'lot_number',
            'material_name', 'project_code', 'current_facility',
            'facility_name', 'status', 'quantity_bricks',
            'sampling_date', 'sampled_by', 'is_counter_sample',
            'notes', 'receipt_record', 'collection_record',
            'photos', 'specimens', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'updated_at']


class SampleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sample
        fields = [
            'id', 'sample_code', 'material_lot', 'current_facility',
            'quantity_bricks', 'sampling_date', 'sampled_by',
            'is_counter_sample', 'notes'
        ]


class SampleReceiptRequestSerializer(serializers.Serializer):
    packaging_condition = serializers.CharField()
    moisture_barrier_intact = serializers.BooleanField(default=True)
    heat_numbers_verified = serializers.BooleanField(default=True)
    remarks = serializers.CharField(required=False, allow_blank=True, default='')


class SpecimenPreparationRequestSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=1, max_value=20)
    geometry = serializers.CharField(max_length=100)
    length_mm = serializers.DecimalField(max_digits=6, decimal_places=2, required=False)
    width_mm = serializers.DecimalField(max_digits=6, decimal_places=2, required=False)
    height_mm = serializers.DecimalField(max_digits=6, decimal_places=2, required=False)
