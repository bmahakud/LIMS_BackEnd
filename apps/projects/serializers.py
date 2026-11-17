from rest_framework import serializers
from .models import Client, Vendor, Project, Material, MaterialLot


class ClientSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='organization.name', read_only=True)
    country = serializers.CharField(source='organization.country', read_only=True)

    class Meta:
        model = Client
        fields = ['id', 'name', 'country', 'industry_segment', 'contact_person', 'contact_email', 'created_at']


class VendorSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='organization.name', read_only=True)
    country = serializers.CharField(source='organization.country', read_only=True)

    class Meta:
        model = Vendor
        fields = ['id', 'name', 'vendor_code', 'country', 'iso_certified', 'created_at']


class ProjectSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.organization.name', read_only=True)

    class Meta:
        model = Project
        fields = ['id', 'code', 'name', 'client', 'client_name', 'plant_asset', 'start_date', 'target_completion', 'is_active', 'created_at']


class MaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Material
        fields = ['id', 'code', 'name', 'category', 'nominal_al2o3_pct', 'nominal_sio2_pct', 'max_service_temp_c']


class MaterialLotSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source='material.name', read_only=True)
    material_code = serializers.CharField(source='material.code', read_only=True)
    project_code = serializers.CharField(source='project.code', read_only=True)
    vendor_name = serializers.CharField(source='vendor.organization.name', read_only=True)

    class Meta:
        model = MaterialLot
        fields = [
            'id', 'lot_number', 'project', 'project_code',
            'material', 'material_name', 'material_code',
            'vendor', 'vendor_name', 'quantity_units',
            'manufacturing_date', 'created_at'
        ]
