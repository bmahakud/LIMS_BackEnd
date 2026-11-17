from rest_framework import viewsets, permissions, filters
from .models import Laboratory, Instrument
from accounts.operational_access import ScopedOperationalMixin
from accounts.models import RoleType
from .serializers import LaboratorySerializer, InstrumentSerializer


class LaboratoryViewSet(ScopedOperationalMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Laboratory.objects.select_related('facility').prefetch_related('instruments').all()
    serializer_class = LaboratorySerializer
    facility_lookup = 'facility_id'
    facility_attr = 'facility_id'
    permission_classes = ScopedOperationalMixin.permission_classes


class InstrumentViewSet(ScopedOperationalMixin, viewsets.ModelViewSet):
    queryset = Instrument.objects.select_related('laboratory__facility', 'area').all()
    serializer_class = InstrumentSerializer
    facility_lookup = 'laboratory__facility_id'
    facility_attr = 'laboratory.facility_id'
    cross_facility_attrs = ('area.facility_id',)
    write_roles = {
        'create': (RoleType.FACILITY_MANAGER, RoleType.LAB_MANAGER),
        'update': (RoleType.FACILITY_MANAGER, RoleType.LAB_MANAGER),
        'partial_update': (RoleType.FACILITY_MANAGER, RoleType.LAB_MANAGER),
    }
    permission_classes = ScopedOperationalMixin.permission_classes
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['asset_tag', 'name', 'manufacturer', 'serial_number']
    ordering_fields = ['asset_tag', 'next_calibration_due']
