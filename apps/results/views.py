from accounts.operational_access import ScopedOperationalMixin
from accounts.models import RoleType
from rest_framework.exceptions import PermissionDenied
from samples.models import SampleStatus
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import TestRun, Measurement, Result, ResultVerification, RetestRequest, VerificationStatus
from .serializers import (
    TestRunSerializer, MeasurementSerializer, ResultSerializer,
    ResultVerificationSerializer, RetestRequestSerializer
)
from .services import CalculationRegistry


class TestRunViewSet(ScopedOperationalMixin, viewsets.ModelViewSet):
    queryset = TestRun.objects.select_related('assignment__specimen', 'instrument', 'technician').prefetch_related('measurements', 'results').all()
    serializer_class = TestRunSerializer
    facility_lookup = "assignment__work_order__laboratory__facility_id"
    facility_attr = "assignment.work_order.laboratory.facility_id"
    cross_facility_attrs = ("instrument.laboratory.facility_id",)
    final_sample_attr = "assignment.specimen.parent_sample"
    write_roles = {"create": (RoleType.LAB_TECHNICIAN,), "update": (RoleType.LAB_TECHNICIAN,), "partial_update": (RoleType.LAB_TECHNICIAN,)}
    permission_classes = ScopedOperationalMixin.permission_classes

    def perform_create(self, serializer):
        self.ensure_write_scope(serializer)
        assignment = serializer.validated_data['assignment']
        if assignment.assigned_technician_id != self.request.user.id:
            raise PermissionDenied('Test runs must be performed by their assigned technician.')
        serializer.save(technician=self.request.user)


class ResultViewSet(ScopedOperationalMixin, viewsets.ModelViewSet):
    queryset = Result.objects.select_related('test_run__assignment__specimen', 'test_method', 'technician').all()
    serializer_class = ResultSerializer
    facility_lookup = "test_run__assignment__work_order__laboratory__facility_id"
    facility_attr = "test_run.assignment.work_order.laboratory.facility_id"
    final_sample_attr = "test_run.assignment.specimen.parent_sample"
    write_roles = {"create": (RoleType.LAB_TECHNICIAN,), "verify_result": (RoleType.QA_REVIEWER, RoleType.AUTHORIZED_APPROVER)}
    permission_classes = ScopedOperationalMixin.permission_classes
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['parameter_code', 'raw_input_text', 'test_run__assignment__specimen__specimen_code']

    def perform_create(self, serializer):
        self.ensure_write_scope(serializer)
        run = serializer.validated_data['test_run']
        if run.technician_id != self.request.user.id:
            raise PermissionDenied('Only the assigned technician can enter results for this run.')
        raw_text = self.request.data.get('raw_input_text', '')
        num_val, qual = CalculationRegistry.parse_qualified_input(raw_text)
        serializer.save(
            technician=self.request.user,
            numeric_value=num_val,
            qualifier=qual
        )

    @action(detail=True, methods=['post'], url_path='verify')
    def verify_result(self, request, pk=None):
        result = self.get_object()
        if result.technician_id == request.user.id:
            raise PermissionDenied("Independent reviewer required: the technician cannot verify their own result.")
        if result.test_run.assignment.specimen.parent_sample.status in (SampleStatus.REPORT_ISSUED, SampleStatus.STORED):
            raise PermissionDenied("Issued results cannot be modified.")
        # Verify permissions: must have can_verify_results
        can_verify = request.user.memberships.filter(is_active=True, role__can_verify_results=True).exists()
        if not can_verify:
            return Response({"detail": "Unauthorized: Lead Metallurgist or QA Director clearance required."}, status=status.HTTP_403_FORBIDDEN)

        comments = request.data.get('comments', '')
        verification, _ = ResultVerification.objects.update_or_create(
            result=result,
            defaults={'verified_by': request.user, 'comments': comments, 'verified_at': timezone.now()}
        )
        result.verification_status = VerificationStatus.VERIFIED
        result.save()
        return Response(ResultSerializer(result).data, status=status.HTTP_200_OK)


class RetestRequestViewSet(ScopedOperationalMixin, viewsets.ModelViewSet):
    queryset = RetestRequest.objects.select_related('original_result', 'requested_by').all()
    serializer_class = RetestRequestSerializer
    facility_lookup = "original_result__test_run__assignment__work_order__laboratory__facility_id"
    facility_attr = "original_result.test_run.assignment.work_order.laboratory.facility_id"
    final_sample_attr = "original_result.test_run.assignment.specimen.parent_sample"
    write_roles = {"create": (RoleType.QA_REVIEWER, RoleType.LAB_MANAGER)}
    permission_classes = ScopedOperationalMixin.permission_classes

    def perform_create(self, serializer):
        self.ensure_write_scope(serializer)
        serializer.save(requested_by=self.request.user)
