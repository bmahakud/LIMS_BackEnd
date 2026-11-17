from accounts.operational_access import ScopedOperationalMixin
from accounts.models import RoleType
from rest_framework import viewsets, permissions, filters
from .models import WorkOrder, TestAssignment
from .serializers import WorkOrderSerializer, WorkOrderCreateSerializer, TestAssignmentSerializer


class WorkOrderViewSet(ScopedOperationalMixin, viewsets.ModelViewSet):
    queryset = WorkOrder.objects.select_related('laboratory__facility', 'created_by').prefetch_related('assignments__specimen', 'assignments__test_method').all()
    facility_lookup = "laboratory__facility_id"
    facility_attr = "laboratory.facility_id"
    write_roles = {"create": (RoleType.LAB_MANAGER,), "update": (RoleType.LAB_MANAGER,), "partial_update": (RoleType.LAB_MANAGER,)}
    permission_classes = ScopedOperationalMixin.permission_classes
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['order_number', 'laboratory__name']
    ordering_fields = ['created_at', 'target_completion_date']

    def get_serializer_class(self):
        if self.action == 'create':
            return WorkOrderCreateSerializer
        return WorkOrderSerializer

    def perform_create(self, serializer):
        self.ensure_write_scope(serializer)
        serializer.save(created_by=self.request.user)


class TestAssignmentViewSet(ScopedOperationalMixin, viewsets.ModelViewSet):
    queryset = TestAssignment.objects.select_related('work_order', 'specimen', 'test_method__test_definition', 'instrument', 'assigned_technician').all()
    serializer_class = TestAssignmentSerializer
    facility_lookup = "work_order__laboratory__facility_id"
    facility_attr = "work_order.laboratory.facility_id"
    cross_facility_attrs = ("specimen.parent_sample.current_facility_id", "instrument.laboratory.facility_id")
    write_roles = {"create": (RoleType.LAB_MANAGER,), "update": (RoleType.LAB_MANAGER,), "partial_update": (RoleType.LAB_MANAGER,)}
    permission_classes = ScopedOperationalMixin.permission_classes
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['specimen__specimen_code', 'test_method__standard_code', 'work_order__order_number']
