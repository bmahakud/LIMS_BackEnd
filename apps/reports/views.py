from accounts.operational_access import ScopedOperationalMixin
from accounts.models import RoleType
from django.http import HttpResponse
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from .models import LaboratoryReport, ConsolidatedReport, ReportRevision
from .serializers import LaboratoryReportSerializer, ConsolidatedReportSerializer, IssueReportRequestSerializer
from .services import ReportingService
from samples.models import Sample
from test_catalogue.models import SpecificationSet


class LaboratoryReportViewSet(ScopedOperationalMixin, viewsets.ReadOnlyModelViewSet):
    queryset = LaboratoryReport.objects.select_related('sample', 'issued_by').all()
    serializer_class = LaboratoryReportSerializer
    facility_lookup = "sample__current_facility_id"
    facility_attr = "sample.current_facility_id"
    write_roles = {"issue_report": (RoleType.AUTHORIZED_APPROVER,)}
    permission_classes = ScopedOperationalMixin.permission_classes

    @action(detail=False, methods=['post'], url_path='issue')
    def issue_report(self, request):
        req_serializer = IssueReportRequestSerializer(data=request.data)
        if not req_serializer.is_valid():
            return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = req_serializer.validated_data
        try:
            sample = Sample.objects.get(id=data['sample_id'])
            spec_set = SpecificationSet.objects.get(id=data['specification_set_id'])
        except Exception:
            return Response({"detail": "Sample or SpecificationSet not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            report = ReportingService.issue_laboratory_report(
                sample=sample,
                approver=request.user,
                outcome=data['outcome'],
                decision_notes=data['decision_notes'],
                specification_set=spec_set
            )
            return Response(LaboratoryReportSerializer(report).data, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({"detail": str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'], url_path='pdf')
    def download_pdf(self, request, pk=None):
        report = self.get_object()
        buffer = ReportingService.generate_pdf_buffer(report.report_snapshot_json)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{report.report_number}.pdf"'
        return response


class ConsolidatedReportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ConsolidatedReport.objects.select_related('project', 'approved_by').prefetch_related('samples').all()
    serializer_class = ConsolidatedReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from accounts.operational_access import authorized_facility_ids
        ids = authorized_facility_ids(self.request.user)
        queryset = super().get_queryset()
        if not ids:
            return queryset.none()
        # A report is visible only when every included sample is in scope.
        from organizations.models import Facility
        foreign_facilities = Facility.objects.exclude(id__in=ids).values_list('id', flat=True)
        return queryset.filter(samples__current_facility_id__in=ids).exclude(
            samples__current_facility_id__in=foreign_facilities
        ).distinct()
