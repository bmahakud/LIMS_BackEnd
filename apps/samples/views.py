from accounts.operational_access import ScopedOperationalMixin, role_in_facility
from accounts.models import RoleType
from rest_framework.exceptions import PermissionDenied
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from .models import Sample, Specimen, SampleReceipt
from .serializers import (
    SampleSerializer, SampleCreateSerializer, SpecimenSerializer,
    SampleReceiptSerializer, SampleReceiptRequestSerializer,
    SpecimenPreparationRequestSerializer
)
from .services import SampleLifecycleService


class SampleViewSet(ScopedOperationalMixin, viewsets.ModelViewSet):
    queryset = Sample.objects.select_related(
        'material_lot__material', 'material_lot__project', 'current_facility'
    ).prefetch_related('specimens', 'photos', 'receipt_record', 'collection_record').all()
    facility_lookup = "current_facility_id"
    facility_attr = "current_facility.id"
    write_roles = {
        "create": (RoleType.SAMPLE_CLERK, RoleType.INSPECTOR, RoleType.LAB_MANAGER),
        "update": (RoleType.SAMPLE_CLERK, RoleType.LAB_MANAGER),
        "partial_update": (RoleType.SAMPLE_CLERK, RoleType.LAB_MANAGER),
        "record_receipt": (RoleType.SAMPLE_CLERK, RoleType.LAB_MANAGER),
        "prepare_specimens": (RoleType.LAB_TECHNICIAN, RoleType.LAB_MANAGER),
    }
    permission_classes = ScopedOperationalMixin.permission_classes
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['sample_code', 'material_lot__lot_number', 'material_lot__material__name']
    ordering_fields = ['created_at', 'sample_code', 'status']

    def get_serializer_class(self):
        if self.action == 'create':
            return SampleCreateSerializer
        return SampleSerializer

    @action(detail=True, methods=['post'], url_path='receipt')
    def record_receipt(self, request, pk=None):
        sample = self.get_object()
        req_serializer = SampleReceiptRequestSerializer(data=request.data)
        if not req_serializer.is_valid():
            return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = req_serializer.validated_data
        try:
            receipt = SampleLifecycleService.record_receipt(
                sample=sample,
                user=request.user,
                packaging_condition=data['packaging_condition'],
                moisture_barrier_intact=data['moisture_barrier_intact'],
                heat_numbers_verified=data['heat_numbers_verified'],
                remarks=data.get('remarks', '')
            )
            sample.refresh_from_db()
            return Response(SampleSerializer(sample).data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='prepare-specimens')
    def prepare_specimens(self, request, pk=None):
        sample = self.get_object()
        req_serializer = SpecimenPreparationRequestSerializer(data=request.data)
        if not req_serializer.is_valid():
            return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = req_serializer.validated_data
        dims = {
            'length': data.get('length_mm'),
            'width': data.get('width_mm'),
            'height': data.get('height_mm')
        }
        try:
            specimens = SampleLifecycleService.prepare_child_specimens(
                sample=sample,
                count=data['count'],
                geometry=data['geometry'],
                dimensions=dims
            )
            return Response(SpecimenSerializer(specimens, many=True).data, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SpecimenViewSet(ScopedOperationalMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Specimen.objects.select_related('parent_sample').all()
    serializer_class = SpecimenSerializer
    facility_lookup = 'parent_sample__current_facility_id'
    facility_attr = 'parent_sample.current_facility_id'
    permission_classes = ScopedOperationalMixin.permission_classes
    filter_backends = [filters.SearchFilter]
    search_fields = ['specimen_code', 'parent_sample__sample_code']
